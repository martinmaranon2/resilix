"""
Incident coordinator: connects the voice agent, the background agent and the operator.

Architecture
------------
One ``IncidentCoordinator`` serves one call:
1. The voice agent talks to the caller and creates the incident card.
2. The coordinator starts the background agent in a worker thread, with the task built
   from the call. ``update_incident`` keeps one incident per call, so both agents work
   on the same card.
3. Approval-tier tools of the background agent create pending actions for the operator.
4. An approval listener turns every approved action of this incident into a short
   update text; ``deliver_updates`` pushes the waiting updates into the call as
   [SYSTEM UPDATE] between caller turns, so the voice agent can tell the caller what
   is coming. Rejected or failed actions are not told to the caller.

Use cases
---------
1. Demo: the caller hears "the ambulance arrives in about 3 minutes" right after the
   operator approves the dispatch that the background agent proposed.
2. Operator console: the same listener can update the screen.
"""

import asyncio
import threading
from typing import Any, Dict, List, Optional

from alpineguard.agents.background_agent import BackgroundIncidentAgent, build_incident_task
from alpineguard.agents.voice_agent import VoiceCallSession
from alpineguard.models.agent_runs import AgentRunResult
from alpineguard.models.approvals import ApprovalStatus, PendingAction
from alpineguard.tools.registry import ToolRegistry


def describe_approved_action(action: PendingAction) -> str:
    """
    Turn an approved action into a short update for the voice agent.

    Parameters:
        action: Action with status EXECUTED.

    Returns:
        One or two sentences with what was approved and arrival times, if known.
    """
    text = f"The operator approved: {action.summary}"
    rows: List[Dict[str, Any]] = action.preview.get("units") or action.preview.get("responders") or []
    etas = [f"{r['name']} about {round(r['eta_minutes'])} min" for r in rows if r.get("eta_minutes") is not None]
    if etas:
        text += " Estimated arrival: " + ", ".join(etas) + "."
    return text


class IncidentCoordinator:
    """Runs the background agent next to a voice call and forwards approvals into the call."""

    def __init__(self, registry: ToolRegistry, call: VoiceCallSession, background: Optional[BackgroundIncidentAgent] = None) -> None:
        """
        Create the coordinator.

        Parameters:
            registry: Shared tool registry (same context for both agents).
            call: Open voice call session.
            background: Background agent; created on the same registry when None.
        """
        self.registry = registry
        self.call = call
        self.background = background or BackgroundIncidentAgent(registry)
        self.incident_id: Optional[str] = None
        self.background_result: Optional[AgentRunResult] = None
        self.delivered: List[str] = []
        self._updates: List[str] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        registry.ctx.approvals.add_listener(self._on_decision)

    def _call_incident_ids(self) -> List[str]:
        return [i.id for i in self.registry.ctx.incidents.values() if self.call.call_id in i.call_ids]

    def _on_decision(self, action: PendingAction) -> None:
        if action.status == ApprovalStatus.EXECUTED and action.incident_id in self._call_incident_ids():
            with self._lock:
                self._updates.append(describe_approved_action(action))

    def start_background(self) -> None:
        """Start the background agent for the call in a worker thread."""
        ctx = self.registry.ctx
        ids = self._call_incident_ids()
        self.incident_id = ids[0] if ids else None
        note = (
            f"\nThe voice agent already created incident {self.incident_id} for this call and is coaching the caller. "
            f"Update that incident with update_incident(incident_id='{self.incident_id}', ...); do not create a new one."
            if self.incident_id else
            "\nThe voice agent is coaching the caller. Create the incident card for this call."
        )
        task = build_incident_task(ctx.world, [self.call.call_id]) + note

        def work() -> None:
            self.background_result = self.background.run(task)

        self._thread = threading.Thread(target=work, name="background-agent", daemon=True)
        self._thread.start()

    @property
    def background_running(self) -> bool:
        """True while the background agent works."""
        return self._thread is not None and self._thread.is_alive()

    async def deliver_updates(self) -> int:
        """
        Push all waiting approval updates into the call.

        Returns:
            Number of updates delivered.
        """
        with self._lock:
            updates, self._updates = self._updates, []
        for text in updates:
            await self.call.push_update(text)
            self.delivered.append(text)
        return len(updates)

    async def wait_for_background(self, timeout_s: float = 300.0) -> Optional[AgentRunResult]:
        """
        Wait until the background agent has finished.

        Parameters:
            timeout_s: Maximum wait.

        Returns:
            The background agent's result, or None when it has not finished in time.
        """
        if self._thread is not None:
            await asyncio.to_thread(self._thread.join, timeout_s)
        return self.background_result
