"""
Time helpers for AlpineGuard.

Architecture
------------
New AlpineGuard code uses timezone-aware UTC timestamps. These helpers create them,
parse the ISO-8601 timestamps in scenario files, and turn datetimes into strings for
JSON tool results and audit entries.

Use cases
---------
1. Stamp audit entries, approvals and public alerts with the current UTC time.
2. Parse scenario timestamps such as "2026-08-14T16:10:30+02:00".
3. Serialize datetimes in ``to_dict`` methods.
"""

from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """
    Return the current time as a timezone-aware UTC datetime.

    Returns:
        Current UTC time.
    """
    return datetime.now(timezone.utc)


def to_iso(value: Optional[datetime]) -> Optional[str]:
    """
    Convert a datetime to an ISO-8601 string.

    Parameters:
        value: Datetime to convert, or None.

    Returns:
        ISO-8601 string, or None when value is None.
    """
    return value.isoformat() if value is not None else None


def parse_iso(value: str) -> datetime:
    """
    Parse an ISO-8601 timestamp with a UTC offset into an aware datetime.

    Parameters:
        value: Timestamp with offset, for example "2026-08-14T16:10:30+02:00".

    Returns:
        Timezone-aware datetime.

    Raises:
        ValueError: If the string is not ISO-8601 or has no UTC offset.
    """
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp '{value}' has no UTC offset")
    return parsed
