"""
Tool metadata types for the AlpineGuard agent tool layer.

Architecture
------------
Every tool that an agent may call is described by a ``ToolSpec``: its name, the
description and JSON schema that Gemini sees, its tier (the agent runs it alone, or the
operator must approve it) and the agent roles that may call it. The registry in
``alpineguard.tools.registry`` turns specs into Gemini function declarations, checks the
arguments, runs the handlers and sends approval-tier tools to the approval queue.

Use cases
---------
1. Give the voice agent only fast tools and the background agent all tools.
2. Mark the action tools that must wait for operator approval.
3. Refer to tools with ``ToolName`` members instead of raw strings.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List


class ToolName(str, Enum):
    """Names of all tools that agents can call."""

    # Core tools (all incident types)
    LOCATE_CALLER = "locate_caller"
    UPDATE_INCIDENT = "update_incident"
    FIND_RELATED_INCIDENTS = "find_related_incidents"
    GET_PROTOCOL = "get_protocol"
    LIST_UNITS = "list_units"
    PROPOSE_DISPATCH = "propose_dispatch"
    NOTIFY_CENTRE = "notify_centre"
    HANDOFF_TO_OPERATOR = "handoff_to_operator"
    # Cardiac arrest tools
    FIND_AED = "find_aed"
    ALERT_FIRST_RESPONDERS = "alert_first_responders"
    FIND_HOSPITAL = "find_hospital"
    # Forest fire tools
    GET_FIRE_DATA = "get_fire_data"
    GET_WEATHER = "get_weather"
    ANALYZE_IMAGE = "analyze_image"
    PREDICT_SPREAD = "predict_spread"
    ESTIMATE_EXPOSURE = "estimate_exposure"
    PLAN_EVACUATION = "plan_evacuation"
    DRAFT_PUBLIC_ALERT = "draft_public_alert"
    REQUEST_INFRA_ACTION = "request_infra_action"
    MAKE_ROUTE_CARD = "make_route_card"


class ToolTier(str, Enum):
    """Who decides that a tool's effect happens."""

    AGENT_ALONE = "agent_alone"
    OPERATOR_APPROVES = "operator_approves"


class AgentRole(str, Enum):
    """Agent that calls a tool."""

    VOICE = "voice"            # talks to the caller; gets only fast tools
    BACKGROUND = "background"  # prepares the incident for the operator; gets all tools


class ToolResultStatus(str, Enum):
    """Status field of every tool result."""

    OK = "ok"
    ERROR = "error"
    PENDING_APPROVAL = "pending_approval"


@dataclass
class ToolSpec:
    """
    Description of one agent tool.

    Attributes:
        name: Tool name that Gemini calls.
        description: Text that tells the model when and how to use the tool.
        parameters: JSON schema (type "object") of the tool arguments.
        tier: AGENT_ALONE tools return results directly; OPERATOR_APPROVES tools return a
            ProposedAction that waits in the approval queue.
        roles: Agent roles that may call the tool.
        handler: Python function called as ``handler(ctx, **arguments)``.
    """

    name: ToolName
    description: str
    parameters: Dict[str, Any]
    tier: ToolTier
    roles: List[AgentRole]
    handler: Callable[..., Any]

    def declaration(self) -> Dict[str, Any]:
        """
        Build the provider-neutral function declaration for this tool.

        Returns:
            Dictionary with "name", "description" and "parameters" (JSON schema).
        """
        tier_note = (
            " Needs operator approval: this only creates a pending action."
            if self.tier == ToolTier.OPERATOR_APPROVES
            else ""
        )
        return {
            "name": self.name.value,
            "description": self.description + tier_note,
            "parameters": self.parameters,
        }
