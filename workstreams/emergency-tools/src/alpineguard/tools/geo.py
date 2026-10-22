"""
Geometry helpers for the tool layer (standard library only).

Architecture
------------
The tools work on small areas (a few kilometres). For these, a local flat projection
around a reference point (equirectangular) is accurate enough. All polygon and segment
tests project to metres east/north of the first polygon vertex, then use plane geometry.
Great-circle distances use the haversine formula.

Use cases
---------
1. Distances for ETAs, AED search and related-incident search.
2. Point-in-polygon and segment-crossing tests for exposure and routing.
3. Building the spread ellipse from metre offsets.
"""

import math
from typing import List, Sequence, Tuple

from alpineguard.models.domain import Coordinates

EARTH_RADIUS_M = 6_371_000.0
METRES_PER_DEGREE_LAT = 111_320.0

XY = Tuple[float, float]


def haversine_m(a: Coordinates, b: Coordinates) -> float:
    """
    Great-circle distance between two points.

    Parameters:
        a: First point.
        b: Second point.

    Returns:
        Distance in metres.
    """
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat = lat2 - lat1
    dlon = math.radians(b.longitude - a.longitude)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def bearing_deg(a: Coordinates, b: Coordinates) -> float:
    """
    Compass bearing from a to b.

    Parameters:
        a: Start point.
        b: End point.

    Returns:
        Bearing in degrees (0 = north, 90 = east).
    """
    x, y = to_local_xy(a, b)
    return math.degrees(math.atan2(x, y)) % 360


def to_local_xy(origin: Coordinates, point: Coordinates) -> XY:
    """
    Project a point to metres east (x) and north (y) of an origin.

    Parameters:
        origin: Reference point.
        point: Point to project.

    Returns:
        (x_east_m, y_north_m).
    """
    x = (point.longitude - origin.longitude) * METRES_PER_DEGREE_LAT * math.cos(math.radians(origin.latitude))
    y = (point.latitude - origin.latitude) * METRES_PER_DEGREE_LAT
    return x, y


def from_local_xy(origin: Coordinates, x_east_m: float, y_north_m: float) -> Coordinates:
    """
    Convert metres east/north of an origin back to coordinates.

    Parameters:
        origin: Reference point.
        x_east_m: Metres east of the origin.
        y_north_m: Metres north of the origin.

    Returns:
        Coordinates of the offset point.
    """
    lat = origin.latitude + y_north_m / METRES_PER_DEGREE_LAT
    lon = origin.longitude + x_east_m / (METRES_PER_DEGREE_LAT * math.cos(math.radians(origin.latitude)))
    return Coordinates(latitude=lat, longitude=lon)


def centroid(points: Sequence[Coordinates]) -> Coordinates:
    """
    Mean position of points.

    Parameters:
        points: At least one point.

    Returns:
        Average latitude and longitude.

    Raises:
        ValueError: If points is empty.
    """
    if not points:
        raise ValueError("centroid() needs at least one point")
    return Coordinates(
        latitude=sum(p.latitude for p in points) / len(points),
        longitude=sum(p.longitude for p in points) / len(points),
    )


def _polygon_xy(polygon: Sequence[Coordinates]) -> Tuple[Coordinates, List[XY]]:
    origin = polygon[0]
    return origin, [to_local_xy(origin, p) for p in polygon]


def _point_in_xy_polygon(px: float, py: float, poly: List[XY]) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > py) != (yj > py):
            x_cross = (xj - xi) * (py - yi) / (yj - yi) + xi
            if px < x_cross:
                inside = not inside
        j = i
    return inside


def point_in_polygon(point: Coordinates, polygon: Sequence[Coordinates]) -> bool:
    """
    Test whether a point lies inside a polygon (ray casting).

    Parameters:
        point: Point to test.
        polygon: Polygon vertices (at least 3, not closed).

    Returns:
        True if the point is inside.
    """
    if len(polygon) < 3:
        return False
    origin, poly = _polygon_xy(polygon)
    px, py = to_local_xy(origin, point)
    return _point_in_xy_polygon(px, py, poly)


def _orientation(a: XY, b: XY, c: XY) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: XY, b: XY, c: XY) -> bool:
    return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])


def _segments_intersect(p1: XY, p2: XY, q1: XY, q2: XY) -> bool:
    d1 = _orientation(q1, q2, p1)
    d2 = _orientation(q1, q2, p2)
    d3 = _orientation(p1, p2, q1)
    d4 = _orientation(p1, p2, q2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 != 0 and d2 != 0 and d3 != 0 and d4 != 0:
        return True
    if d1 == 0 and _on_segment(q1, q2, p1):
        return True
    if d2 == 0 and _on_segment(q1, q2, p2):
        return True
    if d3 == 0 and _on_segment(p1, p2, q1):
        return True
    if d4 == 0 and _on_segment(p1, p2, q2):
        return True
    return False


def _distance_point_segment(p: XY, a: XY, b: XY) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length_sq))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def segment_crosses_polygon(a: Coordinates, b: Coordinates, polygon: Sequence[Coordinates]) -> bool:
    """
    Test whether a segment touches a polygon (an end inside or an edge crossing).

    Parameters:
        a: Segment start.
        b: Segment end.
        polygon: Polygon vertices.

    Returns:
        True if any part of the segment is inside or on the polygon.
    """
    if len(polygon) < 3:
        return False
    origin, poly = _polygon_xy(polygon)
    pa, pb = to_local_xy(origin, a), to_local_xy(origin, b)
    if _point_in_xy_polygon(pa[0], pa[1], poly) or _point_in_xy_polygon(pb[0], pb[1], poly):
        return True
    n = len(poly)
    return any(_segments_intersect(pa, pb, poly[i], poly[(i + 1) % n]) for i in range(n))


def path_crosses_polygon(path: Sequence[Coordinates], polygon: Sequence[Coordinates]) -> bool:
    """
    Test whether a polyline touches a polygon.

    Parameters:
        path: Polyline points (at least 1).
        polygon: Polygon vertices.

    Returns:
        True if any point or segment of the path is inside or crosses the polygon.
    """
    if len(path) == 1:
        return point_in_polygon(path[0], polygon)
    return any(segment_crosses_polygon(path[i], path[i + 1], polygon) for i in range(len(path) - 1))


def distance_to_polygon_m(point: Coordinates, polygon: Sequence[Coordinates]) -> float:
    """
    Distance from a point to a polygon.

    Parameters:
        point: Point.
        polygon: Polygon vertices.

    Returns:
        0 if the point is inside, otherwise the distance to the nearest edge in metres.
    """
    if len(polygon) < 3:
        return float("inf")
    origin, poly = _polygon_xy(polygon)
    p = to_local_xy(origin, point)
    if _point_in_xy_polygon(p[0], p[1], poly):
        return 0.0
    n = len(poly)
    return min(_distance_point_segment(p, poly[i], poly[(i + 1) % n]) for i in range(n))


def segment_distance_to_polygon_m(a: Coordinates, b: Coordinates, polygon: Sequence[Coordinates]) -> float:
    """
    Smallest distance between a segment and a polygon.

    Parameters:
        a: Segment start.
        b: Segment end.
        polygon: Polygon vertices.

    Returns:
        0 if the segment touches the polygon, otherwise the smallest distance in metres.
    """
    if len(polygon) < 3:
        return float("inf")
    if segment_crosses_polygon(a, b, polygon):
        return 0.0
    origin, poly = _polygon_xy(polygon)
    pa, pb = to_local_xy(origin, a), to_local_xy(origin, b)
    n = len(poly)
    edge_distances = [
        min(_distance_point_segment(pa, poly[i], poly[(i + 1) % n]), _distance_point_segment(pb, poly[i], poly[(i + 1) % n]))
        for i in range(n)
    ]
    vertex_distances = [_distance_point_segment(v, pa, pb) for v in poly]
    return min(min(edge_distances), min(vertex_distances))


def polygon_area_km2(polygon: Sequence[Coordinates]) -> float:
    """
    Area of a polygon (shoelace formula on the local projection).

    Parameters:
        polygon: Polygon vertices.

    Returns:
        Area in square kilometres.
    """
    if len(polygon) < 3:
        return 0.0
    _, poly = _polygon_xy(polygon)
    n = len(poly)
    twice_area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))
    return abs(twice_area) / 2 / 1_000_000
