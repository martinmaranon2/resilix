"""
Protocol types: approved questions and caller instructions.

Architecture
------------
Agents must not invent medical or safety advice. They read questions and instructions
only from protocol files in ``alpineguard/protocols`` (one JSON file per incident
category). Each file names its sources and its approval status. In this demo the files
are based on public guidelines and are NOT approved by a medical director or fire service.

Use cases
---------
1. The voice agent reads telephone CPR steps to a caller.
2. The voice agent tells a caller near a forest fire how to move away safely.
3. The operator console shows which source an instruction came from.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from alpineguard.models.domain import IncidentCategory


@dataclass
class ProtocolSource:
    """A public source that a protocol is based on."""

    title: str
    url: Optional[str] = None
    reference: Optional[str] = None
    published: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the source to a dictionary without empty fields.

        Returns:
            Source fields that have a value.
        """
        data = {
            "title": self.title,
            "url": self.url,
            "reference": self.reference,
            "published": self.published,
            "note": self.note,
        }
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class Protocol:
    """Approved questions and instructions for one incident category."""

    protocol_id: str
    category: IncidentCategory
    title: str
    approval_status: str
    sources: List[ProtocolSource]
    questions: List[str]
    instructions: List[str]
    recognition: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the protocol to a dictionary.

        Returns:
            Protocol fields with category as string.
        """
        return {
            "protocol_id": self.protocol_id,
            "category": self.category.value,
            "title": self.title,
            "approval_status": self.approval_status,
            "sources": [s.to_dict() for s in self.sources],
            "recognition": self.recognition,
            "questions": self.questions,
            "instructions": self.instructions,
        }
