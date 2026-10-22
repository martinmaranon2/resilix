"""
Call, social media and coordination message types.

Architecture
------------
These dataclasses describe what reaches the emergency centre (phone calls with their
AML position and transcript, social media posts) and what the agents send out
(information for other centres, hand-offs to a human operator). The simulated world
loads calls and posts from scenario files; later a telephony gateway fills the same types.

Use cases
---------
1. ``locate_caller`` reads the AML position of an ``IncomingCall``.
2. ``find_related_incidents`` groups calls and ``SocialPost`` items about one event.
3. ``notify_centre`` and ``handoff_to_operator`` record ``CentreMessage`` and ``HandoffRequest``.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from alpineguard.models.domain import Coordinates
from alpineguard.time_utils import to_iso


class EmergencyCentre(str, Enum):
    """Swiss emergency numbers; each number is answered by its own centre."""

    POLICE_117 = "117"
    FIRE_118 = "118"
    AMBULANCE_144 = "144"
    POISON_145 = "145"
    REGA_1414 = "1414"


class Language(str, Enum):
    """Languages for caller instructions and public alerts."""

    DE = "de"
    FR = "fr"
    IT = "it"
    EN = "en"


class LocationSource(str, Enum):
    """How the caller position was obtained."""

    AML = "aml"  # Advanced Mobile Location: the phone sends its GPS position with the call
    CELL_ID = "cell_id"
    CALLER_DESCRIBED = "caller_described"


class HandoffUrgency(str, Enum):
    """How fast a human operator must take over."""

    IMMEDIATE = "immediate"
    SOON = "soon"


@dataclass
class IncomingCall:
    """An emergency call with caller position and transcript."""

    call_id: str
    centre: EmergencyCentre
    received_at: datetime
    language: Language
    location: Coordinates
    location_accuracy_m: float
    location_source: LocationSource
    address_hint: str
    caller_number_masked: str
    transcript: List[str]
    is_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the call to a dictionary without the transcript.

        Returns:
            Call metadata; the transcript is left out on purpose (privacy).
        """
        return {
            "call_id": self.call_id,
            "centre": self.centre.value,
            "received_at": to_iso(self.received_at),
            "language": self.language.value,
            "location": self.location.to_dict(),
            "location_accuracy_m": self.location_accuracy_m,
            "location_source": self.location_source.value,
            "address_hint": self.address_hint,
            "is_simulated": self.is_simulated,
        }


@dataclass
class SocialPost:
    """A public social media post about a possible incident."""

    post_id: str
    platform: str
    posted_at: datetime
    text: str
    location: Optional[Coordinates] = None
    is_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the post to a dictionary.

        Returns:
            Post fields; location is None when the post has no position.
        """
        return {
            "post_id": self.post_id,
            "platform": self.platform,
            "posted_at": to_iso(self.posted_at),
            "text": self.text,
            "location": self.location.to_dict() if self.location else None,
            "is_simulated": self.is_simulated,
        }


@dataclass
class CentreMessage:
    """Information that an agent sends to another emergency centre."""

    message_id: str
    centre: EmergencyCentre
    incident_id: str
    text: str
    sent_at: datetime
    sent_by: str

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the message to a dictionary.

        Returns:
            Message fields with the centre number as string.
        """
        return {
            "message_id": self.message_id,
            "centre": self.centre.value,
            "incident_id": self.incident_id,
            "text": self.text,
            "sent_at": to_iso(self.sent_at),
            "sent_by": self.sent_by,
        }


@dataclass
class HandoffRequest:
    """A request that a human operator takes over a call or incident."""

    handoff_id: str
    reason: str
    urgency: HandoffUrgency
    created_at: datetime
    incident_id: Optional[str] = None
    call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the hand-off to a dictionary.

        Returns:
            Hand-off fields with urgency as string.
        """
        return {
            "handoff_id": self.handoff_id,
            "reason": self.reason,
            "urgency": self.urgency.value,
            "created_at": to_iso(self.created_at),
            "incident_id": self.incident_id,
            "call_id": self.call_id,
        }
