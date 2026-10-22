"""
Evacuation route card drawn by code (SVG), not by a generative model.

Architecture
------------
An image model can draw roads that do not exist; a wrong road on an evacuation map can
send people towards the fire. The route card is therefore drawn from the routing result:
the predicted fire area (red), the route line (green), the waypoints, the start and the
assembly point (blue), walking time and distance. Coordinates are projected to the card
with a local flat projection. Labels exist in DE, FR, IT and EN.

Use cases
---------
1. ``make_route_card`` writes the card for a caller's phone or the public alert page.
2. A generative model may later add only pictograms around this card, never geometry.
"""

from html import escape
from typing import Dict, List, Optional, Sequence, Tuple

from alpineguard.config import Config
from alpineguard.models.calls import Language
from alpineguard.models.domain import Coordinates, EvacuationRoute
from alpineguard.tools.geo import to_local_xy

_LABELS: Dict[Language, Dict[str, str]] = {
    Language.DE: {"title": "Evakuierungsroute", "start": "Start", "goal": "Sammelplatz",
                  "fire": "Brandgebiet (Prognose +{h} min)", "walk": "{km} km, ca. {min} min zu Fuss",
                  "note": "Aus Routendaten gezeichnet. Anweisungen von Polizei und Feuerwehr befolgen."},
    Language.FR: {"title": "Itinéraire d'évacuation", "start": "Départ", "goal": "Point de rassemblement",
                  "fire": "Zone du feu (prévision +{h} min)", "walk": "{km} km, env. {min} min à pied",
                  "note": "Dessiné à partir des données d'itinéraire. Suivez les consignes de la police et des pompiers."},
    Language.IT: {"title": "Percorso di evacuazione", "start": "Partenza", "goal": "Punto di raccolta",
                  "fire": "Zona dell'incendio (previsione +{h} min)", "walk": "{km} km, circa {min} min a piedi",
                  "note": "Disegnato dai dati del percorso. Seguire le istruzioni di polizia e pompieri."},
    Language.EN: {"title": "Evacuation route", "start": "Start", "goal": "Assembly point",
                  "fire": "Fire area (forecast +{h} min)", "walk": "{km} km, about {min} min on foot",
                  "note": "Drawn from route data. Follow the instructions of police and fire brigade."},
}


def _project(points: Sequence[Coordinates], width: int, height: int, margin: int) -> Tuple[List[Tuple[float, float]], Coordinates]:
    origin = points[0]
    xy = [to_local_xy(origin, p) for p in points]
    min_x, max_x = min(x for x, _ in xy), max(x for x, _ in xy)
    min_y, max_y = min(y for _, y in xy), max(y for _, y in xy)
    span = max(max_x - min_x, max_y - min_y, 1.0)
    scale = min(width - 2 * margin, height - 2 * margin - 80) / span
    projected = [(margin + (x - min_x) * scale, margin + 60 + (max_y - y) * scale) for x, y in xy]
    return projected, origin


def render_route_card_svg(
    route: EvacuationRoute,
    hazard_polygon: Optional[Sequence[Coordinates]],
    horizon_minutes: Optional[int],
    language: Language,
) -> str:
    """
    Draw the route card as an SVG document.

    Parameters:
        route: Evacuation route with waypoints.
        hazard_polygon: Predicted fire area to show, or None.
        horizon_minutes: Forecast horizon of the fire area (for the legend).
        language: Language of the labels.

    Returns:
        SVG document as text.
    """
    labels = _LABELS[language]
    width, height, margin = Config.ROUTE_CARD_WIDTH_PX, Config.ROUTE_CARD_HEIGHT_PX, Config.ROUTE_CARD_MARGIN_PX
    route_points = [w.coordinates for w in route.waypoints]
    hazard = list(hazard_polygon or [])
    projected, _ = _project(route_points + hazard, width, height, margin)
    route_xy = projected[: len(route_points)]
    hazard_xy = projected[len(route_points):]

    parts: List[str] = [
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {height}' width='{width}' height='{height}'>",
        f"<rect width='{width}' height='{height}' fill='#ffffff'/>",
        f"<text x='{margin}' y='34' font-family='sans-serif' font-size='24' font-weight='bold' fill='#111111'>"
        f"{escape(labels['title'])}</text>",
        f"<text x='{margin}' y='58' font-family='sans-serif' font-size='16' fill='#333333'>"
        f"{escape(route.waypoints[0].name)} → {escape(route.waypoints[-1].name)}</text>",
    ]
    if hazard_xy:
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in hazard_xy)
        parts.append(f"<polygon points='{points}' fill='#d7263d' fill-opacity='0.35' stroke='#d7263d' stroke-width='2'/>")
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in route_xy)
    parts.append(f"<polyline points='{line}' fill='none' stroke='#1b998b' stroke-width='6' stroke-linejoin='round'/>")
    for index, ((x, y), waypoint) in enumerate(zip(route_xy, route.waypoints)):
        is_start, is_goal = index == 0, index == len(route_xy) - 1
        colour = "#111111" if is_start else ("#2e5eaa" if is_goal else "#1b998b")
        radius = 9 if (is_start or is_goal) else 5
        parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{radius}' fill='{colour}'/>")
        prefix = f"{labels['start']}: " if is_start else (f"{labels['goal']}: " if is_goal else "")
        parts.append(
            f"<text x='{x + 12:.1f}' y='{y + 5:.1f}' font-family='sans-serif' font-size='14' fill='{colour}'>"
            f"{escape(prefix + waypoint.name)}</text>"
        )
    legend_y = height - 50
    walk = labels["walk"].format(km=f"{route.total_distance_km:.1f}", min=route.estimated_walking_time_mins)
    parts.append(f"<text x='{margin}' y='{legend_y}' font-family='sans-serif' font-size='16' fill='#111111'>{escape(walk)}</text>")
    if hazard_xy and horizon_minutes is not None:
        parts.append(
            f"<text x='{width - margin}' y='{legend_y}' text-anchor='end' font-family='sans-serif' font-size='16' "
            f"fill='#d7263d'>{escape(labels['fire'].format(h=horizon_minutes))}</text>"
        )
    parts.append(f"<text x='{margin}' y='{height - 20}' font-family='sans-serif' font-size='12' fill='#555555'>{escape(labels['note'])}</text>")
    parts.append(f"<text x='{width - 30}' y='70' text-anchor='middle' font-family='sans-serif' font-size='16' fill='#111111'>N</text>")
    parts.append(f"<line x1='{width - 30}' y1='100' x2='{width - 30}' y2='76' stroke='#111111' stroke-width='2'/>")
    parts.append("</svg>")
    return "\n".join(parts)
