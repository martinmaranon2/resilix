"""
Routing types: path network, assembly points and route plans.

Architecture
------------
The evacuation planner works on a small network of named places (nodes) and paths
(edges: footpaths, roads, cable cars). It removes every node and edge that is inside or
too close to the predicted fire area and searches the fastest way to an assembly point
that is reachable and big enough. The result is a ``RoutePlan``, which the
``plan_evacuation`` tool turns into the existing ``EvacuationRoute`` type.

Use cases
---------
1. Load the scenario path network into ``RoadNode`` and ``RoadEdge`` records.
2. Choose an assembly point by reachability and capacity.
3. Explain to the operator why other assembly points were not chosen.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from alpineguard.models.domain import Coordinates


class PathKind(str, Enum):
    """Kind of connection between two nodes."""

    FOOTPATH = "footpath"
    ROAD = "road"
    CABLE_CAR = "cable_car"


class DestinationRejection(str, Enum):
    """Why an assembly point was not chosen."""

    BLOCKED_BY_HAZARD = "blocked_by_hazard"
    CAPACITY_TOO_SMALL = "capacity_too_small"
    NOT_REACHABLE = "not_reachable"
    LONGER_THAN_CHOSEN = "longer_than_chosen"


@dataclass
class RoadNode:
    """A named place in the path network."""

    node_id: str
    name: str
    location: Coordinates


@dataclass
class RoadEdge:
    """A connection between two nodes; usable in both directions."""

    from_node_id: str
    to_node_id: str
    name: str
    kind: PathKind
    length_m: Optional[float] = None


@dataclass
class AssemblyPoint:
    """A safe place where evacuated people gather."""

    point_id: str
    name: str
    node_id: str
    location: Coordinates
    capacity: int
    is_simulated: bool = True


@dataclass
class RejectedDestination:
    """An assembly point that the planner did not choose, and why."""

    point_id: str
    name: str
    reason: DestinationRejection

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the rejection to a dictionary.

        Returns:
            Rejection fields with the reason as string.
        """
        return {"point_id": self.point_id, "name": self.name, "reason": self.reason.value}


@dataclass
class RoutePlan:
    """Fastest safe path from a start node to an assembly point."""

    node_ids: List[str]
    edges: List[RoadEdge]
    leg_minutes: List[float]
    leg_lengths_m: List[float]
    total_length_m: float
    total_minutes: float
    destination: AssemblyPoint
    rejected_destinations: List[RejectedDestination] = field(default_factory=list)
