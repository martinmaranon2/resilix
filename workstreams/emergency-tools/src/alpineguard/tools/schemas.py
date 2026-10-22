"""
Reusable JSON schema pieces for tool parameters.

Architecture
------------
Many tools take the same kinds of arguments (positions, incident ids, reasons, enum
values). Defining them once keeps descriptions and limits identical across tools. Enum
schemas are built from the Python enums, so Gemini sees exactly the allowed values.

Use cases
---------
1. ``LATITUDE`` and ``LONGITUDE`` in every position-based tool.
2. ``enum_schema(UnitKind, ...)`` for unit kinds in ``list_units``.
3. ``REASON`` in every approval-tier tool.
"""

from enum import Enum
from typing import Any, Dict, Type

LATITUDE: Dict[str, Any] = {"type": "number", "description": "Latitude in WGS84 degrees.", "minimum": -90, "maximum": 90}
LONGITUDE: Dict[str, Any] = {"type": "number", "description": "Longitude in WGS84 degrees.", "minimum": -180, "maximum": 180}
INCIDENT_ID: Dict[str, Any] = {"type": "string", "description": "Incident id returned by update_incident."}
REASON: Dict[str, Any] = {
    "type": "string",
    "description": "Short, specific reason with the facts that support the action; the operator reads it on the approval card.",
}
MAX_RESULTS: Dict[str, Any] = {"type": "integer", "description": "Maximum number of results.", "minimum": 1, "maximum": 20}


def enum_schema(enum_type: Type[Enum], description: str) -> Dict[str, Any]:
    """
    Build a string schema that allows exactly the values of an enum.

    Parameters:
        enum_type: Enum whose values are strings or ints.
        description: Description for the model.

    Returns:
        JSON schema with "enum".
    """
    values = [member.value for member in enum_type]
    value_type = "integer" if all(isinstance(v, int) for v in values) else "string"
    return {"type": value_type, "description": description, "enum": values}


def object_schema(properties: Dict[str, Any], required: list) -> Dict[str, Any]:
    """
    Build an object schema for tool parameters.

    Parameters:
        properties: Property schemas by name.
        required: Names of required properties.

    Returns:
        JSON schema of type "object".
    """
    return {"type": "object", "properties": properties, "required": required}
