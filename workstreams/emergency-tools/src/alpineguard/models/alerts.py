"""
Public alert types.

Architecture
------------
The agent drafts a public alert (texts per language, alert area, severity). The draft
waits in the approval queue; only an approved draft is published (simulated
Alertswiss channel). The texts are written by the agent; the operator reads and
approves them on the approval card.

Use cases
---------
1. Evacuation order for the area of a predicted forest fire.
2. Warning to avoid an area (smoke, closed forest).
3. Shelter-in-place instruction when no safe route exists.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from alpineguard.models.calls import Language
from alpineguard.models.domain import Coordinates, SeverityLevel
from alpineguard.time_utils import to_iso, utc_now


class PublicAlertKind(str, Enum):
    """What the public alert tells people to do."""

    EVACUATE = "evacuate"
    AVOID_AREA = "avoid_area"
    SHELTER_IN_PLACE = "shelter_in_place"


class AlertStatus(str, Enum):
    """Publication status of an alert."""

    DRAFT = "draft"
    PUBLISHED = "published"


@dataclass
class AlertText:
    """Alert text in one language."""

    language: Language
    headline: str
    instruction: str

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the text to a dictionary.

        Returns:
            Text fields with the language code.
        """
        return {"language": self.language.value, "headline": self.headline, "instruction": self.instruction}


@dataclass
class PublicAlertDraft:
    """A public alert; published only after operator approval."""

    alert_id: str
    incident_id: str
    channel: str
    alert_kind: PublicAlertKind
    severity: SeverityLevel
    area_polygon: List[Coordinates]
    area_description: str
    texts: List[AlertText]
    status: AlertStatus = AlertStatus.DRAFT
    created_at: datetime = field(default_factory=utc_now)
    published_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the alert to a dictionary (polygon as vertex count only).

        Returns:
            Alert fields.
        """
        return {
            "alert_id": self.alert_id,
            "incident_id": self.incident_id,
            "channel": self.channel,
            "alert_kind": self.alert_kind.value,
            "severity": self.severity.value,
            "area_description": self.area_description,
            "area_polygon_vertex_count": len(self.area_polygon),
            "texts": [t.to_dict() for t in self.texts],
            "status": self.status.value,
            "created_at": to_iso(self.created_at),
            "published_at": to_iso(self.published_at),
        }
