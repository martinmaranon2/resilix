"""
Result helpers shared by all tool handlers.

Architecture
------------
Every tool returns a JSON-ready dictionary with a ``status`` field ("ok", "error" or
"pending_approval"). Handlers use ``ok`` and ``error`` to build results and raise
``ToolInputError`` when the agent's input cannot be used; the registry turns that error
into an error result, so the model can correct its call.

Use cases
---------
1. ``return ok(units=rows)`` in a data tool.
2. ``raise ToolInputError("Unknown incident_id 'x'")`` in an approval tool.
3. ``new_id("inc")`` for incident, route and alert ids.
"""

import uuid
from typing import Any, Dict

from alpineguard.models.tooling import ToolResultStatus


class ToolInputError(Exception):
    """The agent's tool input cannot be used; the message is sent back to the agent."""


def ok(**data: Any) -> Dict[str, Any]:
    """
    Build a successful tool result.

    Parameters:
        **data: Result fields (JSON-ready values).

    Returns:
        Dictionary with status "ok" and the given fields.
    """
    return {"status": ToolResultStatus.OK.value, **data}


def error(message: str, **data: Any) -> Dict[str, Any]:
    """
    Build an error tool result.

    Parameters:
        message: What went wrong and, if possible, how to fix the call.
        **data: Extra JSON-ready fields.

    Returns:
        Dictionary with status "error", the message and the given fields.
    """
    return {"status": ToolResultStatus.ERROR.value, "error": message, **data}


def new_id(prefix: str) -> str:
    """
    Create a short random id with a prefix.

    Parameters:
        prefix: Id prefix, for example "inc" or "route".

    Returns:
        Id such as "inc-3f9a1c2b".
    """
    return f"{prefix}-{uuid.uuid4().hex[:8]}"
