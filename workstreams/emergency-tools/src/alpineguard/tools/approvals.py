"""
Approval queue: actions wait here until a human operator decides.

Architecture
------------
Approval-tier tools and the supervisor agent submit a ``ProposedAction``. The queue
stores it as a ``PendingAction`` and keeps its executor function separately. Only
``approve(action_id, operator_id)`` runs the executor; ``reject`` closes the action
without effect. Every step is written to the audit trail with the operator's id. An
executor that fails (for example because a unit is no longer available) leaves the
action in status FAILED with the error text.

Use cases
---------
1. Operator console lists ``pending()`` actions as approval cards.
2. Operator approves a dispatch: the units change to DISPATCHED in the world.
3. Operator rejects a public alert: nothing is published.
4. Listeners (``add_listener``) forward decisions, for example to the voice agent in the call.
"""

import uuid
from typing import Any, Callable, Dict, List, Optional

from alpineguard.audit import AuditLog, logger
from alpineguard.models.approvals import ApprovalStatus, PendingAction, ProposedAction
from alpineguard.models.audit import AuditEventKind
from alpineguard.models.tooling import ToolName
from alpineguard.time_utils import utc_now


class ApprovalQueue:
    """Queue of actions that need a human decision."""

    def __init__(self, audit: AuditLog) -> None:
        """
        Create an empty queue.

        Parameters:
            audit: Audit trail for requests and decisions.
        """
        self._audit = audit
        self._actions: Dict[str, PendingAction] = {}
        self._executors: Dict[str, Callable[[], Dict[str, Any]]] = {}
        self._listeners: List[Callable[[PendingAction], None]] = []

    def add_listener(self, listener: Callable[[PendingAction], None]) -> None:
        """
        Register a function that is called after every operator decision.

        Parameters:
            listener: Called with the decided action (EXECUTED, FAILED or REJECTED).
        """
        self._listeners.append(listener)

    def _notify(self, action: PendingAction) -> None:
        for listener in self._listeners:
            try:
                listener(action)
            except Exception:  # a broken listener must not undo the decision
                logger.exception("Approval listener failed for %s", action.action_id)

    def submit(
        self,
        tool_name: ToolName,
        arguments: Dict[str, Any],
        reason: str,
        requested_by: str,
        proposal: ProposedAction,
    ) -> PendingAction:
        """
        Store a proposed action as pending.

        Parameters:
            tool_name: Tool that proposed the action.
            arguments: Arguments of the tool call (for the record).
            reason: Why the agent proposes the action.
            requested_by: Agent or component that proposed it.
            proposal: Summary, preview and executor of the action.

        Returns:
            The new pending action.
        """
        action = PendingAction(
            action_id=f"act-{uuid.uuid4().hex[:8]}",
            tool_name=tool_name,
            arguments=arguments,
            reason=reason,
            summary=proposal.summary,
            incident_id=proposal.incident_id,
            requested_by=requested_by,
            preview=proposal.preview,
        )
        self._actions[action.action_id] = action
        self._executors[action.action_id] = proposal.executor
        self._audit.record(
            AuditEventKind.APPROVAL_REQUESTED,
            actor=requested_by,
            name=action.action_id,
            details={"tool": tool_name.value, "summary": proposal.summary, "preview": proposal.preview},
            reason=reason,
            incident_id=proposal.incident_id,
        )
        return action

    def get(self, action_id: str) -> PendingAction:
        """
        Look up an action.

        Parameters:
            action_id: Id returned by ``submit``.

        Returns:
            The action.

        Raises:
            ValueError: If the id is unknown.
        """
        if action_id not in self._actions:
            raise ValueError(f"Unknown action_id '{action_id}'")
        return self._actions[action_id]

    def pending(self, incident_id: Optional[str] = None) -> List[PendingAction]:
        """
        List actions that wait for a decision.

        Parameters:
            incident_id: Only actions of this incident, if given.

        Returns:
            Pending actions in submission order.
        """
        return [
            a for a in self._actions.values()
            if a.status == ApprovalStatus.PENDING and (incident_id is None or a.incident_id == incident_id)
        ]

    def all(self) -> List[PendingAction]:
        """
        List all actions in submission order, whatever their status.

        Returns:
            All actions.
        """
        return list(self._actions.values())

    def approve(self, action_id: str, operator_id: str, note: Optional[str] = None) -> PendingAction:
        """
        Approve an action and run it.

        Parameters:
            action_id: Action to approve.
            operator_id: Id of the human operator who approves (required).
            note: Optional operator note.

        Returns:
            The action with status EXECUTED or FAILED.

        Raises:
            ValueError: If the id is unknown, the operator id is empty or the action is not pending.
        """
        action = self._require_pending(action_id, operator_id)
        action.status = ApprovalStatus.APPROVED
        action.decided_at = utc_now()
        action.decided_by = operator_id
        action.decision_note = note
        self._audit.record(
            AuditEventKind.APPROVAL_GRANTED, actor=f"operator:{operator_id}", name=action_id,
            details={"tool": action.tool_name.value, "summary": action.summary, "note": note},
            incident_id=action.incident_id,
        )
        try:
            action.result = self._executors[action_id]()
            action.status = ApprovalStatus.EXECUTED
            self._audit.record(
                AuditEventKind.ACTION_EXECUTED, actor=f"operator:{operator_id}", name=action_id,
                details={"tool": action.tool_name.value, "result": action.result},
                incident_id=action.incident_id,
            )
        except Exception as exc:  # executor failures must not crash the console
            if isinstance(exc, ValueError):  # expected: for example the unit was taken meanwhile
                logger.warning("Executor of %s failed: %s", action_id, exc)
            else:
                logger.exception("Executor of %s failed", action_id)
            action.status = ApprovalStatus.FAILED
            action.error = f"{type(exc).__name__}: {exc}"
            self._audit.record(
                AuditEventKind.ACTION_FAILED, actor=f"operator:{operator_id}", name=action_id,
                details={"tool": action.tool_name.value, "error": action.error},
                incident_id=action.incident_id,
            )
        self._notify(action)
        return action

    def reject(self, action_id: str, operator_id: str, note: Optional[str] = None) -> PendingAction:
        """
        Reject an action; nothing is executed.

        Parameters:
            action_id: Action to reject.
            operator_id: Id of the human operator who rejects (required).
            note: Optional reason of the operator.

        Returns:
            The action with status REJECTED.

        Raises:
            ValueError: If the id is unknown, the operator id is empty or the action is not pending.
        """
        action = self._require_pending(action_id, operator_id)
        action.status = ApprovalStatus.REJECTED
        action.decided_at = utc_now()
        action.decided_by = operator_id
        action.decision_note = note
        self._audit.record(
            AuditEventKind.APPROVAL_REJECTED, actor=f"operator:{operator_id}", name=action_id,
            details={"tool": action.tool_name.value, "summary": action.summary, "note": note},
            incident_id=action.incident_id,
        )
        self._notify(action)
        return action

    def _require_pending(self, action_id: str, operator_id: str) -> PendingAction:
        if not operator_id or not operator_id.strip():
            raise ValueError("An operator id is required to decide on an action")
        action = self.get(action_id)
        if action.status != ApprovalStatus.PENDING:
            raise ValueError(f"Action '{action_id}' is not pending (status: {action.status.value})")
        return action
