"""
Arrival time estimates for units and people on foot.

Architecture
------------
ETAs are estimates: straight-line distance, times a road factor for ground units,
divided by an average speed, plus a turnout time per unit kind. Airborne units fly the
straight line. All factors and speeds are in ``Config``. A routing service can replace
this module later without changing the tools.

Use cases
---------
1. Sort available units by ETA in ``list_units``.
2. Show ETAs on dispatch and first-responder approval cards.
3. Walking time to the nearest AED in ``find_aed``.
"""

from alpineguard.config import Config
from alpineguard.models.domain import Coordinates
from alpineguard.models.resources import AIRBORNE_UNIT_KINDS, UnitKind
from alpineguard.tools.geo import haversine_m


def unit_eta_minutes(kind: UnitKind, origin: Coordinates, target: Coordinates) -> float:
    """
    Estimated arrival time of a unit.

    Parameters:
        kind: Unit kind (decides speed, turnout time and road factor).
        origin: Current unit position.
        target: Incident position.

    Returns:
        Minutes until arrival, including turnout time.
    """
    distance_km = haversine_m(origin, target) / 1000.0
    path_km = distance_km if kind in AIRBORNE_UNIT_KINDS else distance_km * Config.ROAD_DISTANCE_FACTOR
    return Config.UNIT_TURNOUT_MINUTES[kind] + path_km / Config.UNIT_SPEED_KMH[kind] * 60.0


def drive_minutes(origin: Coordinates, target: Coordinates) -> float:
    """
    Estimated ambulance driving time without turnout (for hospital choice).

    Parameters:
        origin: Start position.
        target: Destination position.

    Returns:
        Minutes of driving.
    """
    distance_km = haversine_m(origin, target) / 1000.0 * Config.ROAD_DISTANCE_FACTOR
    return distance_km / Config.UNIT_SPEED_KMH[UnitKind.AMBULANCE] * 60.0


def urban_walking_minutes(origin: Coordinates, target: Coordinates) -> float:
    """
    Estimated walking time in a town or station.

    Parameters:
        origin: Start position.
        target: Destination position.

    Returns:
        Minutes of walking (one way).
    """
    distance_km = haversine_m(origin, target) / 1000.0 * Config.WALKING_DETOUR_FACTOR
    return distance_km / Config.URBAN_WALKING_SPEED_KMH * 60.0
