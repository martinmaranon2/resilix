"""
Audit trail and logging for AlpineGuard tools and agents.

Architecture
------------
``AuditLog`` keeps every tool call, approval decision and Gemini call as an
``AuditEntry`` in memory and writes it to the ``alpineguard`` logger at INFO level
(team rule 5 in AGENTS.md). ``sanitize_for_log`` cuts long strings, removes binary data
and hides values whose key looks like a secret before anything is logged.
The tool registry and the approval queue write to the log automatically, so an agent
cannot skip it.

Use cases
---------
1. Operator console panel "what the agent does in the background".
2. Record-keeping log for high-risk AI (EU AI Act Art. 12): who proposed, who approved.
3. ``log_genai_call`` records model, prompt, configuration and output of Gemini calls.
"""

import logging
import sys
import uuid
from typing import Any, Dict, List, Optional

from alpineguard.config import Config
from alpineguard.models.audit import AuditEntry, AuditEventKind

logger = logging.getLogger("alpineguard")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(_handler)
    logger.setLevel(Config.LOG_LEVEL)

_SECRET_KEY_PARTS = ("api_key", "apikey", "access_token", "auth_token", "refresh_token", "authorization",
                     "password", "secret")


def sanitize_for_log(value: Any, max_chars: int = Config.LOG_MAX_VALUE_CHARS) -> Any:
    """
    Make a value safe and short for logging.

    Parameters:
        value: Any JSON-like value (dict, list, str, number, bytes).
        max_chars: Maximum length of a string before it is cut.

    Returns:
        A copy with bytes replaced by a size note, long strings cut, long lists shortened
        and values of secret-looking keys replaced by "<redacted>".
    """
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes removed>"
    if isinstance(value, str):
        if len(value) > max_chars:
            return f"{value[:max_chars]}... [{len(value) - max_chars} more chars]"
        return value
    if isinstance(value, dict):
        clean: Dict[str, Any] = {}
        for key, item in value.items():
            if any(part in str(key).lower() for part in _SECRET_KEY_PARTS):
                clean[str(key)] = "<redacted>"
            else:
                clean[str(key)] = sanitize_for_log(item, max_chars)
        return clean
    if isinstance(value, (list, tuple)):
        items = [sanitize_for_log(item, max_chars) for item in list(value)[:10]]
        if len(value) > 10:
            items.append(f"... {len(value) - 10} more items")
        return items
    return value


class AuditLog:
    """In-memory audit trail that also writes every entry to the logger."""

    def __init__(self) -> None:
        """Create an empty audit trail."""
        self._entries: List[AuditEntry] = []

    def record(
        self,
        kind: AuditEventKind,
        actor: str,
        name: str,
        details: Dict[str, Any],
        reason: Optional[str] = None,
        incident_id: Optional[str] = None,
    ) -> AuditEntry:
        """
        Add one entry to the audit trail and log it at INFO level.

        Parameters:
            kind: Kind of event.
            actor: Who acted, for example "background_agent" or "operator:op-17".
            name: Tool name, action id or model name.
            details: Event details; sanitized before storing.
            reason: Reason given by the actor, if any.
            incident_id: Incident the event belongs to, if any.

        Returns:
            The stored audit entry.
        """
        entry = AuditEntry(
            entry_id=f"audit-{uuid.uuid4().hex[:8]}",
            kind=kind,
            actor=actor,
            name=name,
            details=sanitize_for_log(details),
            reason=reason,
            incident_id=incident_id,
        )
        self._entries.append(entry)
        logger.info(
            "AUDIT %s | actor=%s | name=%s | incident=%s | reason=%s | details=%s",
            kind.value, actor, name, incident_id, reason, entry.details,
        )
        return entry

    def entries(
        self, incident_id: Optional[str] = None, kind: Optional[AuditEventKind] = None
    ) -> List[AuditEntry]:
        """
        Return audit entries in the order they were recorded.

        Parameters:
            incident_id: Only entries of this incident, if given.
            kind: Only entries of this kind, if given.

        Returns:
            Matching entries.
        """
        return [
            e for e in self._entries
            if (incident_id is None or e.incident_id == incident_id) and (kind is None or e.kind == kind)
        ]


def log_genai_call(
    audit: Optional[AuditLog],
    actor: str,
    model: str,
    prompt: Any,
    config: Dict[str, Any],
    output: Any,
) -> None:
    """
    Log one Gemini call with model, prompt, configuration and output.

    Parameters:
        audit: Audit trail to record into; when None, only the logger is used.
        actor: Agent or tool that made the call.
        model: Model identifier, for example "gemini-3.8-flash".
        prompt: Prompt text or a summary of the multi-part prompt (no image bytes).
        config: Generation configuration (tools, system instruction summary, etc.).
        output: Text output and/or function calls of the model.
    """
    details = {"prompt": prompt, "config": config, "output": output}
    if audit is not None:
        audit.record(AuditEventKind.GENAI_CALL, actor=actor, name=model, details=details)
    else:
        logger.info("GENAI %s | actor=%s | details=%s", model, actor, sanitize_for_log(details))
