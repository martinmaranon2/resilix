"""
Checking of tool arguments against the tool's JSON schema.

Architecture
------------
Gemini fills tool arguments from the function declaration, but it can still send a
wrong type, an unknown key or a value outside an enum. The registry calls
``validate_arguments`` before every handler. Problems go back to the model as an error
result, so it can correct the call instead of crashing the handler. Numbers that Gemini
sends as floats (for example 4.0) are turned into ints where the schema says "integer".

Supported schema subset: type (object, string, number, integer, boolean, array), enum,
properties, required, items, minItems, minimum, maximum.

Use cases
---------
1. Reject ``severity = 7`` when the schema allows 1..5.
2. Reject ``unit_kind = "tank"`` when it is not a ``UnitKind`` value.
3. Report a missing required argument by name.
"""

from typing import Any, Dict, List, Tuple


def validate_arguments(schema: Dict[str, Any], args: Dict[str, Any], path: str = "") -> Tuple[Dict[str, Any], List[str]]:
    """
    Check and coerce the arguments of a tool call.

    Parameters:
        schema: JSON schema of type "object".
        args: Arguments sent by the model.
        path: Prefix for problem messages (used for nested objects).

    Returns:
        (coerced arguments, list of problems). The list is empty when the call is valid.
    """
    problems: List[str] = []
    properties: Dict[str, Any] = schema.get("properties", {})
    coerced: Dict[str, Any] = {}
    for key in schema.get("required", []):
        if args.get(key) is None:
            problems.append(f"missing required argument '{path}{key}'")
    for key, value in args.items():
        if key not in properties:
            problems.append(f"unknown argument '{path}{key}'")
            continue
        if value is None:
            continue
        coerced_value, value_problems = _check_value(properties[key], value, f"{path}{key}")
        problems.extend(value_problems)
        coerced[key] = coerced_value
    return coerced, problems


def _check_value(prop: Dict[str, Any], value: Any, name: str) -> Tuple[Any, List[str]]:
    problems: List[str] = []
    expected = prop.get("type")
    if expected == "integer":
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if isinstance(value, bool) or not isinstance(value, int):
            return value, [f"'{name}' must be an integer"]
    elif expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return value, [f"'{name}' must be a number"]
        value = float(value)
    elif expected == "string":
        if not isinstance(value, str):
            return value, [f"'{name}' must be a string"]
    elif expected == "boolean":
        if not isinstance(value, bool):
            return value, [f"'{name}' must be true or false"]
    elif expected == "array":
        if not isinstance(value, (list, tuple)):
            return value, [f"'{name}' must be a list"]
        items_schema = prop.get("items", {})
        checked = []
        for index, item in enumerate(value):
            item_value, item_problems = _check_value(items_schema, item, f"{name}[{index}]")
            problems.extend(item_problems)
            checked.append(item_value)
        if len(checked) < prop.get("minItems", 0):
            problems.append(f"'{name}' needs at least {prop['minItems']} item(s)")
        value = checked
    elif expected == "object":
        if not isinstance(value, dict):
            return value, [f"'{name}' must be an object"]
        value, nested_problems = validate_arguments(prop, dict(value), path=f"{name}.")
        problems.extend(nested_problems)

    if "enum" in prop and value not in prop["enum"]:
        problems.append(f"'{name}' must be one of {prop['enum']}, got {value!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in prop and value < prop["minimum"]:
            problems.append(f"'{name}' must be >= {prop['minimum']}")
        if "maximum" in prop and value > prop["maximum"]:
            problems.append(f"'{name}' must be <= {prop['maximum']}")
    return value, problems
