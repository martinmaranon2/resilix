"""
Exposure types: places with people, infrastructure assets and trains.

Architecture
------------
``estimate_exposure`` checks which sites, infrastructure assets and trains lie in a
predicted fire area. ``request_infra_action`` changes the status of an asset after
operator approval (hold trains, close a road, switch off a power line). The mapping
tables below say which action fits which asset kind and which status follows.

Use cases
---------
1. Count people at risk (visitors on a summit, houses at a forest edge).
2. Find rail lines, roads and power lines that cross the predicted fire area.
3. Hold trains on a threatened line section after the operator approves.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

from alpineguard.models.domain import Coordinates


class SiteKind(str, Enum):
    """Kind of place where people are."""

    CARE_HOME = "care_home"
    SCHOOL = "school"
    RESIDENTIAL_AREA = "residential_area"
    VISITOR_SITE = "visitor_site"
    TRAIN_STATION = "train_station"
    HIKING_TRAIL = "hiking_trail"


class InfraAssetKind(str, Enum):
    """Kind of infrastructure asset."""

    RAIL_LINE = "rail_line"
    ROAD = "road"
    POWER_LINE = "power_line"


class AssetStatus(str, Enum):
    """Operating status of an infrastructure asset."""

    NORMAL = "normal"
    TRAINS_HELD = "trains_held"
    CLOSED = "closed"
    SWITCHED_OFF = "switched_off"


class InfraActionKind(str, Enum):
    """Action that an infrastructure operator can take."""

    HOLD_TRAINS = "hold_trains"
    CLOSE_ROAD = "close_road"
    SWITCH_OFF_POWER_LINE = "switch_off_power_line"


class TrainStatus(str, Enum):
    """Operating status of a train."""

    RUNNING = "running"
    HELD = "held"


# The only action that fits each asset kind.
ACTION_FOR_ASSET_KIND: Dict[InfraAssetKind, InfraActionKind] = {
    InfraAssetKind.RAIL_LINE: InfraActionKind.HOLD_TRAINS,
    InfraAssetKind.ROAD: InfraActionKind.CLOSE_ROAD,
    InfraAssetKind.POWER_LINE: InfraActionKind.SWITCH_OFF_POWER_LINE,
}

# Asset status after an approved action.
STATUS_AFTER_ACTION: Dict[InfraActionKind, AssetStatus] = {
    InfraActionKind.HOLD_TRAINS: AssetStatus.TRAINS_HELD,
    InfraActionKind.CLOSE_ROAD: AssetStatus.CLOSED,
    InfraActionKind.SWITCH_OFF_POWER_LINE: AssetStatus.SWITCHED_OFF,
}


@dataclass
class Site:
    """A place where people are, with an estimate of how many."""

    site_id: str
    name: str
    kind: SiteKind
    location: Coordinates
    people_estimate: int
    is_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the site to a dictionary.

        Returns:
            Site fields.
        """
        return {
            "site_id": self.site_id,
            "name": self.name,
            "kind": self.kind.value,
            "location": self.location.to_dict(),
            "people_estimate": self.people_estimate,
            "is_simulated": self.is_simulated,
        }


@dataclass
class InfraAsset:
    """A rail line, road or power line, as a path of points."""

    asset_id: str
    name: str
    kind: InfraAssetKind
    operator: str
    path: List[Coordinates]
    status: AssetStatus = AssetStatus.NORMAL
    path_is_approximate: bool = True
    is_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the asset to a dictionary (without the path points).

        Returns:
            Asset fields.
        """
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "kind": self.kind.value,
            "operator": self.operator,
            "status": self.status.value,
            "path_point_count": len(self.path),
            "path_is_approximate": self.path_is_approximate,
            "is_simulated": self.is_simulated,
        }


@dataclass
class Train:
    """A train on a rail line asset."""

    train_id: str
    service_name: str
    line_asset_id: str
    location: Coordinates
    heading_to: str
    passengers_estimate: int
    status: TrainStatus = TrainStatus.RUNNING
    is_simulated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the train to a dictionary.

        Returns:
            Train fields.
        """
        return {
            "train_id": self.train_id,
            "service_name": self.service_name,
            "line_asset_id": self.line_asset_id,
            "location": self.location.to_dict(),
            "heading_to": self.heading_to,
            "passengers_estimate": self.passengers_estimate,
            "status": self.status.value,
            "is_simulated": self.is_simulated,
        }
