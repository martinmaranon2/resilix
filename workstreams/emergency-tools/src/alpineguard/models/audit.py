"""
Audit trail types.

Architecture
------------
Every tool call, approval decision and Gemini call becomes one ``AuditEntry``. The
``AuditLog`` in ``alpineguard.audit`` stores the entries in memory and writes them to
the Python logger at INFO level. The operator console can show the entries as the panel
"what the agent does in the background"; they are also the record-keeping log that the
EU AI Act asks for high-risk systems (Art. 12).

Use cases
---------
1. Show the operator which tools the agents called, with arguments and reasons.
2. Prove who approved or rejected each action, and when.
3. Review Gemini prompts and outputs after an incident.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from alpineguard.time_utils import to_iso, utc_now


class AuditEventKind(str, Enum):
    """Kind of event in the audit trail."""

    TOOL_CALL = "tool_call"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"
    ACTION_EXECUTED = "action_executed"
    ACTION_FAILED = "action_failed"
    GENAI_CALL = "genai_call"


@dataclass
class AuditEntry:
    """One event in the audit trail."""

    entry_id: str
    kind: AuditEventKind
    actor: str
    name: str
    details: Dict[str, Any]
    reason: Optional[str] = None
    incident_id: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the entry to a JSON-ready dictionary.

        Returns:
            Dictionary with all fields; enum as value, datetime as ISO string.
        """
        return {
            "entry_id": self.entry_id,
            "kind": self.kind.value,
            "actor": self.actor,
            "name": self.name,
            "details": self.details,
            "reason": self.reason,
            "incident_id": self.incident_id,
            "created_at": to_iso(self.created_at),
        }
