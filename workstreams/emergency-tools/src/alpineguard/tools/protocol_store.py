"""
Loading of approved protocol files.

Architecture
------------
Protocols are JSON files named after the incident category value
(``protocols/cardiac_arrest.json``, ``protocols/wildfire.json``). ``load_protocol``
parses a file into the ``Protocol`` type. A missing file means there is no approved
protocol for the category; the agent must then hand off to the operator instead of
inventing instructions.

Use cases
---------
1. ``get_protocol`` returns questions and instructions to the agents.
2. Tests check that every protocol names its sources and approval status.
"""

import json
from pathlib import Path
from typing import Optional

from alpineguard.config import Config
from alpineguard.models.domain import IncidentCategory
from alpineguard.models.protocols import Protocol, ProtocolSource


def load_protocol(category: IncidentCategory, protocol_dir: Path = Config.PROTOCOL_DIR) -> Optional[Protocol]:
    """
    Load the protocol of an incident category.

    Parameters:
        category: Incident category.
        protocol_dir: Folder with protocol files.

    Returns:
        The protocol, or None when no file exists for the category.

    Raises:
        KeyError, ValueError: If the file exists but misses fields or has a wrong category.
    """
    path = protocol_dir / f"{category.value}.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    protocol = Protocol(
        protocol_id=data["protocol_id"],
        category=IncidentCategory(data["category"]),
        title=data["title"],
        approval_status=data["approval_status"],
        sources=[ProtocolSource(**source) for source in data["sources"]],
        questions=list(data["questions"]),
        instructions=list(data["instructions"]),
        recognition=data.get("recognition"),
    )
    if protocol.category != category:
        raise ValueError(f"Protocol file {path.name} has category '{protocol.category.value}'")
    return protocol
