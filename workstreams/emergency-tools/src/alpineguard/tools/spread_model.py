"""
Simplified forest fire spread model for the demo (ellipse stretched downwind).

Architecture
------------
The fire area after t minutes is drawn as an ellipse:
- head distance  = initial radius + rate * t, with rate = base * (1 + wind factor * wind km/h)
- back distance  = initial radius + rate * backing fraction * t (spread against the wind)
- length-to-breadth ratio = 1 + factor * wind m/s, capped
The ellipse is centred between the back and the head and turned to the downwind bearing.
All constants are in ``Config`` and the result names the model and its limits.

Limits (also in ``Config.SPREAD_MODEL_NOTE``): no slope, fuel, terrain or wind change.
Real fire behaviour models (for example Rothermel-based tools) are needed for operations.

Use cases
---------
1. ``predict_spread`` builds forecasts for +60/+120/+180 minutes.
2. Tests check that the area grows with time and lies downwind of the ignition.
"""

import math
from typing import List, Sequence

from alpineguard.config import Config
from alpineguard.models.domain import Coordinates
from alpineguard.models.fire import SpreadGeometry
from alpineguard.tools.geo import centroid, from_local_xy, haversine_m


def downwind_bearing(wind_from_deg: float) -> float:
    """
    Bearing towards which the wind blows.

    Parameters:
        wind_from_deg: Direction the wind comes from (meteorological convention).

    Returns:
        Downwind bearing in degrees.
    """
    return (wind_from_deg + 180.0) % 360.0


def elliptical_spread(
    ignition_points: Sequence[Coordinates],
    wind_speed_kmh: float,
    wind_from_deg: float,
    minutes: float,
    initial_radius_m: float,
) -> SpreadGeometry:
    """
    Predict the fire area after a number of minutes.

    Parameters:
        ignition_points: Current fire positions (hotspots or the incident position).
        wind_speed_kmh: Mean wind speed.
        wind_from_deg: Direction the wind comes from.
        minutes: Forecast horizon in minutes (> 0).
        initial_radius_m: Size of the current fire area as a radius.

    Returns:
        Polygon and distances of the predicted fire area.

    Raises:
        ValueError: If there is no ignition point or minutes is not positive.
    """
    if not ignition_points:
        raise ValueError("elliptical_spread() needs at least one ignition point")
    if minutes <= 0:
        raise ValueError("Forecast horizon must be positive")

    centre = centroid(ignition_points)
    spread_of_points = max((haversine_m(centre, p) for p in ignition_points), default=0.0)
    r0 = max(initial_radius_m, spread_of_points)

    head_rate = Config.SPREAD_BASE_RATE_M_PER_MIN * (1.0 + Config.SPREAD_WIND_FACTOR_PER_KMH * wind_speed_kmh)
    head = r0 + head_rate * minutes
    back = r0 + head_rate * Config.SPREAD_BACKING_FRACTION * minutes
    wind_m_s = wind_speed_kmh / 3.6
    length_to_breadth = min(
        1.0 + Config.SPREAD_LENGTH_TO_BREADTH_PER_M_S * wind_m_s, Config.SPREAD_MAX_LENGTH_TO_BREADTH
    )
    semi_major = (head + back) / 2.0
    semi_minor = max(semi_major / length_to_breadth, r0)
    centre_offset = (head - back) / 2.0  # ellipse centre lies downwind of the ignition

    bearing = math.radians(downwind_bearing(wind_from_deg))
    along = (math.sin(bearing), math.cos(bearing))     # unit vector downwind (east, north)
    across = (math.cos(bearing), -math.sin(bearing))   # unit vector to the right of downwind

    polygon: List[Coordinates] = []
    for i in range(Config.SPREAD_POLYGON_POINTS):
        theta = 2.0 * math.pi * i / Config.SPREAD_POLYGON_POINTS
        u = centre_offset + semi_major * math.cos(theta)
        v = semi_minor * math.sin(theta)
        east = u * along[0] + v * across[0]
        north = u * along[1] + v * across[1]
        polygon.append(from_local_xy(centre, east, north))

    return SpreadGeometry(
        polygon=polygon,
        head_distance_m=head,
        flank_distance_m=semi_minor,
        back_distance_m=back,
        length_to_breadth=length_to_breadth,
    )
