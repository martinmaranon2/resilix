"""
Evacuation route search that avoids a hazard area.

Architecture
------------
Input: the scenario path network (nodes and edges), a start position, assembly points,
the hazard polygon (predicted fire area) and a safety buffer.
1. Nodes closer to the hazard than the buffer are blocked. The start node is never
   blocked: people must be able to leave it.
2. Edges that come closer to the hazard than the buffer are blocked. When the start
   itself is in the danger zone, an edge from the start node is allowed only if it
   leaves the danger zone within ``EVACUATION_MAX_ESCAPE_M`` and does not enter it again
   (so people are not sent along the fire's path, for example downwind).
3. Dijkstra search by travel time (walking speed; fixed time for cable cars).
4. The nearest reachable assembly point with enough capacity wins; the others are
   reported with the reason why they were not chosen.

Use cases
---------
1. ``plan_evacuation`` for visitors on a summit when the fire blocks the northern paths.
2. Tests check that no waypoint and no leg touches the hazard area.
"""

import heapq
from typing import Dict, List, Optional, Sequence, Tuple

from alpineguard.config import Config
from alpineguard.models.domain import Coordinates
from alpineguard.models.routing import (
    AssemblyPoint,
    DestinationRejection,
    PathKind,
    RejectedDestination,
    RoadEdge,
    RoadNode,
    RoutePlan,
)
from alpineguard.tools.geo import distance_to_polygon_m, haversine_m, segment_distance_to_polygon_m


def edge_length_m(edge: RoadEdge, nodes: Dict[str, RoadNode]) -> float:
    """
    Length of an edge.

    Parameters:
        edge: Edge with optional explicit length.
        nodes: Network nodes by id.

    Returns:
        Explicit length, or straight-line distance x trail/road factor.
    """
    if edge.length_m is not None:
        return edge.length_m
    straight = haversine_m(nodes[edge.from_node_id].location, nodes[edge.to_node_id].location)
    factor = Config.ROAD_DISTANCE_FACTOR if edge.kind == PathKind.ROAD else Config.TRAIL_DISTANCE_FACTOR
    return straight * factor


def edge_minutes(edge: RoadEdge, length_m: float, ascent_m: float = 0.0) -> float:
    """
    Travel time on an edge for people on foot.

    Parameters:
        edge: Edge.
        length_m: Edge length in metres.
        ascent_m: Height gained in the direction of travel (Naismith's rule adds time).

    Returns:
        Minutes (fixed ride time for cable cars).
    """
    if edge.kind == PathKind.CABLE_CAR:
        return Config.CABLE_CAR_RIDE_MINUTES
    flat = length_m / 1000.0 / Config.EVACUATION_WALKING_SPEED_KMH * 60.0
    return flat + max(0.0, ascent_m) / 100.0 * Config.NAISMITH_MINUTES_PER_100M_ASCENT


def _ascent_m(from_node: RoadNode, to_node: RoadNode) -> float:
    if from_node.location.altitude_m is None or to_node.location.altitude_m is None:
        return 0.0
    return max(0.0, to_node.location.altitude_m - from_node.location.altitude_m)


def escape_distance_m(
    a: Coordinates, b: Coordinates, hazard_polygon: Sequence[Coordinates], buffer_m: float
) -> Optional[float]:
    """
    Distance along a segment until it leaves the danger zone for good.

    Parameters:
        a: Segment start (inside the danger zone).
        b: Segment end.
        hazard_polygon: Hazard area.
        buffer_m: Safety buffer around the hazard area.

    Returns:
        Metres from a to the first safe point, or None when the segment never leaves the
        danger zone or enters it again after leaving.
    """
    length = haversine_m(a, b)
    steps = max(2, int(length / Config.EVACUATION_ESCAPE_SAMPLE_STEP_M) + 1)
    exit_at: Optional[float] = None
    for i in range(steps + 1):
        t = i / steps
        point = Coordinates(
            latitude=a.latitude + (b.latitude - a.latitude) * t,
            longitude=a.longitude + (b.longitude - a.longitude) * t,
        )
        safe = distance_to_polygon_m(point, hazard_polygon) >= buffer_m
        if safe and exit_at is None:
            exit_at = t * length
        elif not safe and exit_at is not None:
            return None
    return exit_at


def nearest_node(nodes: Dict[str, RoadNode], position: Coordinates) -> RoadNode:
    """
    Node closest to a position.

    Parameters:
        nodes: Network nodes by id (not empty).
        position: Position.

    Returns:
        Closest node.

    Raises:
        ValueError: If the network has no nodes.
    """
    if not nodes:
        raise ValueError("The path network has no nodes")
    return min(nodes.values(), key=lambda n: haversine_m(n.location, position))


def plan_safe_route(
    nodes: Dict[str, RoadNode],
    edges: Sequence[RoadEdge],
    start: Coordinates,
    assembly_points: Sequence[AssemblyPoint],
    hazard_polygon: Sequence[Coordinates],
    buffer_m: float,
    people_count: Optional[int] = None,
) -> Tuple[Optional[RoutePlan], List[RejectedDestination], RoadNode]:
    """
    Find the fastest safe route to a suitable assembly point.

    Parameters:
        nodes: Network nodes by id.
        edges: Network edges (both directions usable).
        start: Position of the people to evacuate.
        assembly_points: Candidate destinations.
        hazard_polygon: Area to avoid.
        buffer_m: Minimum distance between the route and the hazard area.
        people_count: Number of people; assembly points with less capacity are skipped.

    Returns:
        (route plan or None, rejected destinations, start node).
    """
    start_node = nearest_node(nodes, start)
    blocked_nodes = {
        node_id for node_id, node in nodes.items()
        if node_id != start_node.node_id and distance_to_polygon_m(node.location, hazard_polygon) < buffer_m
    }

    start_is_exposed = distance_to_polygon_m(start_node.location, hazard_polygon) < buffer_m
    adjacency: Dict[str, List[Tuple[str, RoadEdge, float, float]]] = {node_id: [] for node_id in nodes}
    for edge in edges:
        if edge.from_node_id in blocked_nodes or edge.to_node_id in blocked_nodes:
            continue
        too_close = segment_distance_to_polygon_m(
            nodes[edge.from_node_id].location, nodes[edge.to_node_id].location, hazard_polygon
        ) < buffer_m
        if too_close:
            if not (start_is_exposed and start_node.node_id in (edge.from_node_id, edge.to_node_id)):
                continue
            other_id = edge.to_node_id if edge.from_node_id == start_node.node_id else edge.from_node_id
            escape = escape_distance_m(start_node.location, nodes[other_id].location, hazard_polygon, buffer_m)
            if escape is None or escape > Config.EVACUATION_MAX_ESCAPE_M:
                continue
        length = edge_length_m(edge, nodes)
        a, b = nodes[edge.from_node_id], nodes[edge.to_node_id]
        adjacency[edge.from_node_id].append((edge.to_node_id, edge, length, edge_minutes(edge, length, _ascent_m(a, b))))
        adjacency[edge.to_node_id].append((edge.from_node_id, edge, length, edge_minutes(edge, length, _ascent_m(b, a))))

    # Dijkstra by travel time
    best: Dict[str, float] = {start_node.node_id: 0.0}
    previous: Dict[str, Tuple[str, RoadEdge, float, float]] = {}
    queue: List[Tuple[float, str]] = [(0.0, start_node.node_id)]
    while queue:
        minutes_so_far, node_id = heapq.heappop(queue)
        if minutes_so_far > best.get(node_id, float("inf")):
            continue
        for next_id, edge, length, minutes in adjacency[node_id]:
            candidate = minutes_so_far + minutes
            if candidate < best.get(next_id, float("inf")):
                best[next_id] = candidate
                previous[next_id] = (node_id, edge, length, minutes)
                heapq.heappush(queue, (candidate, next_id))

    rejected: List[RejectedDestination] = []
    candidates: List[AssemblyPoint] = []
    for point in assembly_points:
        if point.node_id in blocked_nodes:
            rejected.append(RejectedDestination(point.point_id, point.name, DestinationRejection.BLOCKED_BY_HAZARD))
        elif people_count is not None and point.capacity < people_count:
            rejected.append(RejectedDestination(point.point_id, point.name, DestinationRejection.CAPACITY_TOO_SMALL))
        elif point.node_id not in best:
            rejected.append(RejectedDestination(point.point_id, point.name, DestinationRejection.NOT_REACHABLE))
        else:
            candidates.append(point)

    if not candidates:
        return None, rejected, start_node

    destination = min(candidates, key=lambda p: best[p.node_id])
    for point in candidates:
        if point.point_id != destination.point_id:
            rejected.append(RejectedDestination(point.point_id, point.name, DestinationRejection.LONGER_THAN_CHOSEN))

    node_ids: List[str] = [destination.node_id]
    route_edges: List[RoadEdge] = []
    leg_minutes: List[float] = []
    leg_lengths: List[float] = []
    current = destination.node_id
    while current != start_node.node_id:
        prev_id, edge, length, minutes = previous[current]
        node_ids.append(prev_id)
        route_edges.append(edge)
        leg_minutes.append(minutes)
        leg_lengths.append(length)
        current = prev_id
    node_ids.reverse()
    route_edges.reverse()
    leg_minutes.reverse()
    leg_lengths.reverse()

    plan = RoutePlan(
        node_ids=node_ids,
        edges=route_edges,
        leg_minutes=leg_minutes,
        leg_lengths_m=leg_lengths,
        total_length_m=sum(leg_lengths),
        total_minutes=sum(leg_minutes),
        destination=destination,
        rejected_destinations=rejected,
    )
    return plan, rejected, start_node
