"""
Approval types: actions that wait for a human operator.

Architecture
------------
Under the EU AI Act, AI that classifies emergency calls or sets dispatch priority is
high-risk (Annex III, point 5(d)) and needs human oversight (Art. 14). AlpineGuard
therefore never lets an agent act on the world directly. An approval-tier tool returns a
``ProposedAction`` (summary, preview and an executor function). The approval queue
stores it as a ``PendingAction``; the executor runs only after an operator approves.

Use cases
---------
1. ``propose_dispatch`` proposes units; the operator approves or rejects.
2. ``draft_public_alert`` drafts an Alertswiss message that is published only after approval.
3. The supervisor agent's avalanche flow asks for approval before dispatch and evacuation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional

from alpineguard.models.tooling import ToolName
from alpineguard.time_utils import to_iso, utc_now


class ApprovalStatus(str, Enum):
    """Life cycle of a pending action."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


@dataclass
class ProposedAction:
    """
    What an approval-tier tool returns instead of acting.

    Attributes:
        summary: One sentence the operator reads on the approval card.
        incident_id: Incident the action belongs to, if any.
        preview: Structured details for the approval card (units, ETAs, texts).
        executor: Function that performs the action; called only after approval.
    """

    summary: str
    incident_id: Optional[str]
    preview: Dict[str, Any]
    executor: Callable[[], Dict[str, Any]]


@dataclass
class PendingAction:
    """An action in the approval queue, with its decision record."""

    action_id: str
    tool_name: ToolName
    arguments: Dict[str, Any]
    reason: str
    summary: str
    incident_id: Optional[str]
    requested_by: str
    preview: Dict[str, Any] = field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=utc_now)
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    decision_note: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the pending action to a JSON-ready dictionary.

        Returns:
            Dictionary with all fields; enums as values, datetimes as ISO strings.
        """
        return {
            "action_id": self.action_id,
            "tool_name": self.tool_name.value,
            "arguments": self.arguments,
            "reason": self.reason,
            "summary": self.summary,
            "incident_id": self.incident_id,
            "requested_by": self.requested_by,
            "preview": self.preview,
            "status": self.status.value,
            "created_at": to_iso(self.created_at),
            "decided_at": to_iso(self.decided_at),
            "decided_by": self.decided_by,
            "decision_note": self.decision_note,
            "result": self.result,
            "error": self.error,
        }
