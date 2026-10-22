"""
Types that describe one run of an agent.

Architecture
------------
An agent run is a loop of model turns. In each turn the model either calls tools or
writes its final text. ``AgentRunResult`` records the final text, every tool call with
its result status, the number of turns and why the loop stopped. The operator console
and the end-to-end tests read these records.

Use cases
---------
1. Show the operator the agent's summary and the tools it used.
2. Check in tests which tools the agent called and that no action ran without approval.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentStopReason(str, Enum):
    """Why an agent run ended."""

    FINISHED = "finished"    # the model wrote its final text
    MAX_TURNS = "max_turns"  # the turn limit was reached
    ERROR = "error"          # the model call failed or returned no content


@dataclass
class ToolCallRecord:
    """One tool call made by the agent during a run."""

    turn: int
    name: str
    arguments: Dict[str, Any]
    status: str
    action_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the record to a dictionary.

        Returns:
            Record fields.
        """
        return {"turn": self.turn, "name": self.name, "arguments": self.arguments,
                "status": self.status, "action_id": self.action_id}


@dataclass
class AgentRunResult:
    """Outcome of one agent run."""

    model: str
    final_text: str
    turns: int
    stop_reason: AgentStopReason
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the result to a dictionary.

        Returns:
            Result fields with tool call records.
        """
        return {
            "model": self.model,
            "final_text": self.final_text,
            "turns": self.turns,
            "stop_reason": self.stop_reason.value,
            "tool_calls": [c.to_dict() for c in self.tool_calls],
            "error": self.error,
        }
