"""
Forest fire tools.

Architecture
------------
Nine tools that turn reports of a forest fire into a situation picture and proposed
actions:
- get_fire_data         (agent alone)       satellite hotspots, danger level, available frames
- get_weather           (agent alone)       wind, gusts, temperature, humidity
- analyze_image         (agent alone)       Gemini vision on a frame (scripted when no image file)
- predict_spread        (agent alone)       demo spread model, one forecast per horizon
- estimate_exposure     (agent alone)       people, trains, infrastructure in a forecast area
- plan_evacuation       (agent alone)       safe walking route to an assembly point
- draft_public_alert    (operator approves) Alertswiss message for the forecast area
- request_infra_action  (operator approves) hold trains, close road, switch off power line
- make_route_card       (agent alone)       SVG route card drawn by code
Forecasts, routes, alerts and artifacts are stored in the ``ToolContext`` and referred
to by id, so the model never has to copy polygons.

Use cases
---------
1. Several 118 calls about smoke on the Uetliberg: assess, predict, find who is at risk.
2. Plan a route for 180 summit visitors that avoids the predicted fire area.
3. Propose holding S10 trains and an evacuation alert; the operator approves.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from alpineguard.config import Config
from alpineguard.models.alerts import AlertText, PublicAlertDraft, PublicAlertKind, AlertStatus
from alpineguard.models.approvals import ProposedAction
from alpineguard.models.calls import Language
from alpineguard.models.domain import (
    ArtifactType,
    Coordinates,
    EvacuationRoute,
    EvacuationWaypoint,
    IncidentCategory,
    IncidentStatus,
    MultimodalArtifact,
    SeverityLevel,
)
from alpineguard.models.exposure import ACTION_FOR_ASSET_KIND, InfraActionKind, InfraAssetKind
from alpineguard.models.fire import SpreadForecast
from alpineguard.models.routing import PathKind
from alpineguard.models.tooling import AgentRole, ToolName, ToolSpec, ToolTier
from alpineguard.time_utils import utc_now
from alpineguard.tools.context import ToolContext
from alpineguard.tools.core_tools import get_incident
from alpineguard.tools.geo import (
    centroid,
    distance_to_polygon_m,
    haversine_m,
    path_crosses_polygon,
    point_in_polygon,
    polygon_area_km2,
)
from alpineguard.tools.results import ToolInputError, error, new_id, ok
from alpineguard.tools.route_card import render_route_card_svg
from alpineguard.tools.routing import plan_safe_route
from alpineguard.tools.schemas import INCIDENT_ID, LATITUDE, LONGITUDE, REASON, enum_schema, object_schema
from alpineguard.tools.spread_model import downwind_bearing, elliptical_spread

FORECAST_ID: Dict[str, Any] = {"type": "string", "description": "Forecast id returned by predict_spread."}


def _get_forecast(ctx: ToolContext, forecast_id: str) -> SpreadForecast:
    forecast = ctx.forecasts.get(forecast_id)
    if forecast is None:
        raise ToolInputError(f"Unknown forecast_id '{forecast_id}'. Known forecasts: {sorted(ctx.forecasts)}")
    return forecast


def get_fire_data(ctx: ToolContext, latitude: float, longitude: float, radius_km: Optional[float] = None) -> Dict[str, Any]:
    """
    Return fire hotspots, the forest fire danger level and available frames near a position.

    Parameters:
        ctx: Tool context.
        latitude: Search centre latitude.
        longitude: Search centre longitude.
        radius_km: Search radius (default from Config).

    Returns:
        Hotspots and frames sorted by distance, plus the danger level.
    """
    centre = Coordinates(latitude=latitude, longitude=longitude)
    radius_m = (radius_km if radius_km is not None else Config.FIRE_DATA_RADIUS_KM) * 1000
    hotspots = sorted(
        ({**h.to_dict(), "distance_m": round(haversine_m(centre, h.location))}
         for h in ctx.world.hotspots() if haversine_m(centre, h.location) <= radius_m),
        key=lambda r: r["distance_m"],
    )
    frames = sorted(
        ({**f.to_dict(), "distance_m": round(haversine_m(centre, f.location))}
         for f in ctx.world.frames() if haversine_m(centre, f.location) <= radius_m),
        key=lambda r: r["distance_m"],
    )
    level = ctx.world.fire_danger_level()
    return ok(
        radius_km=radius_m / 1000,
        hotspots=hotspots,
        frames=frames,
        fire_danger_level={"level": level.value, "name": level.name} if level else None,
        note="Use analyze_image with a frame_id to look at a frame.",
    )


def get_weather(ctx: ToolContext, latitude: float, longitude: float) -> Dict[str, Any]:
    """
    Return the weather at a position.

    Parameters:
        ctx: Tool context.
        latitude: Latitude.
        longitude: Longitude.

    Returns:
        Weather snapshot and the downwind bearing.
    """
    weather = ctx.world.weather_at(Coordinates(latitude=latitude, longitude=longitude))
    if weather is None:
        return error("No weather data available for this position.")
    return ok(weather=weather.to_dict(), downwind_bearing_deg=downwind_bearing(weather.wind_from_deg))


def analyze_image(ctx: ToolContext, frame_id: str, question: str) -> Dict[str, Any]:
    """
    Answer a question about a drone or camera frame.

    Parameters:
        ctx: Tool context.
        frame_id: Frame id from get_fire_data.
        question: What to look for.

    Returns:
        Observation text and the method used ("gemini_vision" or "scripted_simulation").
    """
    frame = ctx.world.find_frame(frame_id)
    if frame is None:
        return error(f"Unknown frame_id '{frame_id}'. Known frames: {[f.frame_id for f in ctx.world.frames()]}")
    image_path: Optional[Path] = ctx.world.resolve_image_path(frame)
    if image_path is not None and ctx.vision is not None:
        observation = ctx.vision.analyze(image_path, question)
        method = "gemini_vision"
    else:
        observation = frame.scripted_observation
        method = "scripted_simulation"
    return ok(frame=frame.to_dict(), question=question, observation=observation, method=method)


def predict_spread(
    ctx: ToolContext,
    incident_id: str,
    horizons_minutes: Optional[List[int]] = None,
    initial_radius_m: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Predict the fire area of a wildfire incident for future horizons.

    Parameters:
        ctx: Tool context.
        incident_id: Wildfire incident.
        horizons_minutes: Forecast horizons (default from Config).
        initial_radius_m: Current fire size as a radius (default from Config).

    Returns:
        One forecast summary per horizon; polygons stay in the context.

    Raises:
        ToolInputError: If the incident is unknown, not a wildfire, or there is no weather data.
    """
    incident = get_incident(ctx, incident_id)
    if incident.category != IncidentCategory.WILDFIRE:
        raise ToolInputError(f"Incident '{incident_id}' is not a wildfire (category: {incident.category.value}).")
    hotspots = [
        h for h in ctx.world.hotspots()
        if haversine_m(h.location, incident.coordinates) <= Config.SPREAD_HOTSPOT_SEARCH_RADIUS_M
    ]
    ignition_points = [h.location for h in hotspots] or [incident.coordinates]
    ignition = centroid(ignition_points)
    weather = ctx.world.weather_at(ignition)
    if weather is None:
        raise ToolInputError("No weather data; the spread model needs wind.")
    horizons = sorted(set(horizons_minutes or Config.SPREAD_DEFAULT_HORIZONS_MINUTES))
    if horizons[0] <= 0 or horizons[-1] > Config.SPREAD_MAX_HORIZON_MINUTES:
        raise ToolInputError(f"Horizons must be between 1 and {Config.SPREAD_MAX_HORIZON_MINUTES} minutes.")

    summaries = []
    largest: Optional[SpreadForecast] = None
    for horizon in horizons:
        geometry = elliptical_spread(
            ignition_points, weather.wind_speed_kmh, weather.wind_from_deg, horizon,
            initial_radius_m if initial_radius_m is not None else Config.SPREAD_INITIAL_RADIUS_M,
        )
        forecast = SpreadForecast(
            forecast_id=new_id("fc"),
            incident_id=incident.id,
            horizon_minutes=horizon,
            ignition=ignition,
            polygon=geometry.polygon,
            head_distance_m=geometry.head_distance_m,
            flank_distance_m=geometry.flank_distance_m,
            back_distance_m=geometry.back_distance_m,
            downwind_bearing_deg=downwind_bearing(weather.wind_from_deg),
            wind_speed_kmh=weather.wind_speed_kmh,
            wind_from_deg=weather.wind_from_deg,
            model_name=Config.SPREAD_MODEL_NAME,
            model_note=Config.SPREAD_MODEL_NOTE,
        )
        ctx.forecasts[forecast.forecast_id] = forecast
        largest = forecast
        summaries.append({**forecast.to_dict(include_polygon=False),
                          "area_km2": round(polygon_area_km2(forecast.polygon), 3)})

    assert largest is not None
    incident.hazard_polygon = largest.polygon
    incident.affected_radius_km = round(largest.head_distance_m / 1000, 2)
    incident.updated_at = utc_now()
    return ok(
        incident_id=incident.id,
        ignition_source="satellite hotspots" if hotspots else "incident position",
        ignition=ignition.to_dict(),
        wind={"speed_kmh": weather.wind_speed_kmh, "from_deg": weather.wind_from_deg},
        forecasts=summaries,
        model_name=Config.SPREAD_MODEL_NAME,
        model_note=Config.SPREAD_MODEL_NOTE,
    )


def estimate_exposure(ctx: ToolContext, forecast_id: str) -> Dict[str, Any]:
    """
    List people, trains and infrastructure in or near a forecast fire area.

    Parameters:
        ctx: Tool context.
        forecast_id: Forecast from predict_spread.

    Returns:
        Sites inside and near the area, crossing assets, trains at risk and totals.
    """
    forecast = _get_forecast(ctx, forecast_id)
    polygon = forecast.polygon
    sites_inside, sites_near = [], []
    for site in ctx.world.sites():
        distance = distance_to_polygon_m(site.location, polygon)
        row = {**site.to_dict(), "distance_to_fire_area_m": round(distance)}
        if distance == 0:
            sites_inside.append(row)
        elif distance <= Config.EXPOSURE_NEAR_DISTANCE_M:
            sites_near.append(row)
    crossing = [a for a in ctx.world.assets() if path_crosses_polygon(a.path, polygon)]
    crossing_rail_ids = {a.asset_id for a in crossing if a.kind == InfraAssetKind.RAIL_LINE}
    trains = [
        {**t.to_dict(), "inside_fire_area": point_in_polygon(t.location, polygon)}
        for t in ctx.world.trains()
        if t.line_asset_id in crossing_rail_ids or point_in_polygon(t.location, polygon)
    ]
    return ok(
        forecast_id=forecast.forecast_id,
        horizon_minutes=forecast.horizon_minutes,
        sites_inside=sites_inside,
        sites_near=sites_near,
        near_distance_m=Config.EXPOSURE_NEAR_DISTANCE_M,
        infrastructure_crossing=[{**a.to_dict(), "suggested_action": ACTION_FOR_ASSET_KIND[a.kind].value} for a in crossing],
        trains_at_risk=trains,
        people_inside_estimate=sum(s["people_estimate"] for s in sites_inside),
        train_passengers_at_risk_estimate=sum(t["passengers_estimate"] for t in trains),
        note="People and passenger counts are simulated estimates.",
    )


def plan_evacuation(
    ctx: ToolContext,
    incident_id: str,
    forecast_id: str,
    start_latitude: float,
    start_longitude: float,
    people_count: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Plan a safe walking route that avoids a forecast fire area.

    Parameters:
        ctx: Tool context.
        incident_id: Incident the evacuation belongs to.
        forecast_id: Forecast area to avoid (use the longest horizon).
        start_latitude: Latitude of the people to evacuate.
        start_longitude: Longitude of the people to evacuate.
        people_count: Number of people; assembly points with less capacity are skipped.

    Returns:
        Evacuation route (waypoints, times, warnings) and rejected assembly points.
    """
    incident = get_incident(ctx, incident_id)
    forecast = _get_forecast(ctx, forecast_id)
    nodes = ctx.world.road_nodes()
    if not nodes:
        return error("This scenario has no path network; evacuation routing is not possible.")
    start = Coordinates(latitude=start_latitude, longitude=start_longitude)
    plan, rejected, start_node = plan_safe_route(
        nodes, ctx.world.road_edges(), start, ctx.world.assembly_points(), forecast.polygon,
        Config.EVACUATION_SAFETY_BUFFER_M, people_count,
    )
    if plan is None:
        return error(
            "No safe route to an assembly point with enough capacity. Consider shelter in place and "
            "call handoff_to_operator.",
            rejected_assembly_points=[r.to_dict() for r in rejected],
        )

    waypoints: List[EvacuationWaypoint] = []
    elapsed = 0.0
    ascent = 0.0
    for index, node_id in enumerate(plan.node_ids):
        node = nodes[node_id]
        if index < len(plan.edges):
            edge = plan.edges[index]
            next_name = nodes[plan.node_ids[index + 1]].name
            if edge.kind == PathKind.CABLE_CAR:
                instruction = f"Take the {edge.name} to {next_name}."
            elif index == 0:
                instruction = f"Start at {node.name}. Follow {edge.name} to {next_name}."
            else:
                instruction = f"Continue on {edge.name} to {next_name}."
        else:
            instruction = f"Report to {plan.destination.name}."
        if index > 0:
            prev_alt = nodes[plan.node_ids[index - 1]].location.altitude_m
            if prev_alt is not None and node.location.altitude_m is not None:
                ascent += max(0.0, node.location.altitude_m - prev_alt)
        waypoints.append(EvacuationWaypoint(
            name=node.name,
            coordinates=node.location,
            instruction=instruction,
            hazard_clearance_m=round(distance_to_polygon_m(node.location, forecast.polygon)),
            eta_minutes=int(round(elapsed)),
        ))
        if index < len(plan.leg_minutes):
            elapsed += plan.leg_minutes[index]

    start_alt = nodes[plan.node_ids[0]].location.altitude_m
    end_alt = nodes[plan.node_ids[-1]].location.altitude_m
    warnings = [
        f"Route keeps at least {Config.EVACUATION_SAFETY_BUFFER_M:.0f} m from the forecast fire area "
        f"(+{forecast.horizon_minutes} min, demo spread model).",
        "Follow the instructions of police and fire brigade on site.",
    ]
    needs_fire_brigade_check = ascent > Config.EVACUATION_ASCENT_WARNING_M
    if needs_fire_brigade_check:
        warnings.append(
            f"Route climbs {ascent:.0f} m in total. Fire spreads faster uphill: the fire brigade must confirm "
            "this route before people use it."
        )
    route = EvacuationRoute(
        route_id=new_id("route"),
        incident_id=incident.id,
        safe_destination_name=plan.destination.name,
        safe_destination_coords=plan.destination.location,
        waypoints=waypoints,
        total_distance_km=round(plan.total_length_m / 1000, 2),
        estimated_walking_time_mins=int(round(plan.total_minutes)),
        elevation_drop_m=float(start_alt - end_alt) if start_alt is not None and end_alt is not None else 0.0,
        critical_warnings=warnings,
    )
    ctx.routes[route.route_id] = route
    ctx.route_forecast_ids[route.route_id] = forecast.forecast_id
    return ok(
        route=route.to_dict(),
        start_node=start_node.name,
        avoided_forecast_id=forecast.forecast_id,
        total_ascent_m=round(ascent),
        needs_fire_brigade_check=needs_fire_brigade_check,
        rejected_assembly_points=[r.to_dict() for r in plan.rejected_destinations],
    )


def draft_public_alert(
    ctx: ToolContext,
    incident_id: str,
    forecast_id: str,
    alert_kind: str,
    severity: int,
    area_description: str,
    texts: List[Dict[str, Any]],
    reason: str,
) -> ProposedAction:
    """
    Propose a public alert for a forecast fire area (needs operator approval).

    Parameters:
        ctx: Tool context.
        incident_id: Incident the alert is about.
        forecast_id: Forecast area that the alert covers.
        alert_kind: PublicAlertKind value.
        severity: Severity 1-5.
        area_description: Area in words, for example "Uetliberg summit and forest north of it".
        texts: One object per language with "language", "headline" and "instruction".
        reason: Why the alert is needed now.

    Returns:
        Proposed action whose executor publishes the alert.

    Raises:
        ToolInputError: If ids are unknown or a required language text is missing.
    """
    incident = get_incident(ctx, incident_id)
    forecast = _get_forecast(ctx, forecast_id)
    alert_texts = [AlertText(language=Language(t["language"]), headline=t["headline"], instruction=t["instruction"]) for t in texts]
    required = Config.CANTON_ALERT_LANGUAGES.get(incident.canton, Config.DEFAULT_ALERT_LANGUAGES)
    missing = [lang.value for lang in required if lang not in {t.language for t in alert_texts}]
    if missing:
        raise ToolInputError(f"Alert texts for canton {incident.canton} must include languages {missing}.")
    draft = PublicAlertDraft(
        alert_id=new_id("alert"),
        incident_id=incident.id,
        channel=Config.PUBLIC_ALERT_CHANNEL,
        alert_kind=PublicAlertKind(alert_kind),
        severity=SeverityLevel(severity),
        area_polygon=forecast.polygon,
        area_description=area_description,
        texts=alert_texts,
    )
    ctx.alerts[draft.alert_id] = draft

    def execute() -> Dict[str, Any]:
        draft.status = AlertStatus.PUBLISHED
        draft.published_at = utc_now()
        ctx.world.publish_alert(draft)
        if draft.alert_kind == PublicAlertKind.EVACUATE:
            incident.status = IncidentStatus.EVACUATING
        return {"alert_id": draft.alert_id, "alert_status": draft.status.value, "channel": draft.channel,
                "incident_status": incident.status.value}

    headline = alert_texts[0].headline
    return ProposedAction(
        summary=f"Publish {draft.alert_kind.value} alert \"{headline}\" on {draft.channel} for "
                f"{area_description} (fire forecast +{forecast.horizon_minutes} min).",
        incident_id=incident.id,
        preview=draft.to_dict(),
        executor=execute,
    )


def request_infra_action(
    ctx: ToolContext, incident_id: str, asset_id: str, action: str, reason: str
) -> ProposedAction:
    """
    Propose an infrastructure action (needs operator approval).

    Parameters:
        ctx: Tool context.
        incident_id: Incident the action is about.
        asset_id: Asset from estimate_exposure.
        action: InfraActionKind value that fits the asset kind.
        reason: Why the action is needed.

    Returns:
        Proposed action whose executor changes the asset (and holds trains).

    Raises:
        ToolInputError: If ids are unknown or the action does not fit the asset.
    """
    incident = get_incident(ctx, incident_id)
    asset = ctx.world.find_asset(asset_id)
    if asset is None:
        raise ToolInputError(f"Unknown asset_id '{asset_id}'. Known assets: {[a.asset_id for a in ctx.world.assets()]}")
    requested = InfraActionKind(action)
    fitting = ACTION_FOR_ASSET_KIND[asset.kind]
    if requested != fitting:
        raise ToolInputError(f"Action '{requested.value}' does not fit a {asset.kind.value}; use '{fitting.value}'.")
    trains = [t.to_dict() for t in ctx.world.trains() if t.line_asset_id == asset.asset_id]

    def execute() -> Dict[str, Any]:
        return ctx.world.apply_infra_action(asset.asset_id, requested)

    return ProposedAction(
        summary=f"Ask {asset.operator} to {requested.value.replace('_', ' ')}: {asset.name}.",
        incident_id=incident.id,
        preview={"asset": asset.to_dict(), "action": requested.value, "trains_on_line": trains},
        executor=execute,
    )


def make_route_card(ctx: ToolContext, route_id: str, language: str) -> Dict[str, Any]:
    """
    Draw an SVG route card from a planned route.

    Parameters:
        ctx: Tool context.
        route_id: Route from plan_evacuation.
        language: Language value of the labels.

    Returns:
        Artifact record with the file URL of the SVG.
    """
    route = ctx.routes.get(route_id)
    if route is None:
        return error(f"Unknown route_id '{route_id}'. Known routes: {sorted(ctx.routes)}")
    forecast = ctx.forecasts.get(ctx.route_forecast_ids.get(route_id, ""))
    svg = render_route_card_svg(
        route,
        forecast.polygon if forecast else None,
        forecast.horizon_minutes if forecast else None,
        Language(language),
    )
    artifact_id = new_id("routecard")
    Config.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = Config.ARTIFACT_DIR / f"{artifact_id}.svg"
    path.write_text(svg, encoding="utf-8")
    artifact = MultimodalArtifact(
        artifact_id=artifact_id,
        incident_id=route.incident_id,
        artifact_type=ArtifactType.ROUTE_CARD_SVG,
        media_url=path.as_uri(),
        prompt=f"Drawn by code from route {route_id}; no generative model.",
        metadata={"route_id": route_id, "language": language, "format": "svg", "bytes": len(svg.encode("utf-8"))},
    )
    route.vector_map_render_url = artifact.media_url
    ctx.artifacts[artifact_id] = artifact
    return ok(artifact=artifact.to_dict())


def specs() -> List[ToolSpec]:
    """
    Describe the forest fire tools for the registry.

    Returns:
        Tool specs of the nine forest fire tools.
    """
    background = [AgentRole.BACKGROUND]
    return [
        ToolSpec(
            name=ToolName.GET_FIRE_DATA,
            description="Get satellite fire hotspots, the official forest fire danger level (1-5) and the available "
                        "drone and camera frames near a position.",
            parameters=object_schema({
                "latitude": LATITUDE,
                "longitude": LONGITUDE,
                "radius_km": {"type": "number", "minimum": 0.1, "maximum": 50, "description": "Search radius in km."},
            }, ["latitude", "longitude"]),
            tier=ToolTier.AGENT_ALONE, roles=background, handler=get_fire_data,
        ),
        ToolSpec(
            name=ToolName.GET_WEATHER,
            description="Get wind speed, wind direction (where it comes from), gusts, temperature and humidity at a position.",
            parameters=object_schema({"latitude": LATITUDE, "longitude": LONGITUDE}, ["latitude", "longitude"]),
            tier=ToolTier.AGENT_ALONE, roles=background, handler=get_weather,
        ),
        ToolSpec(
            name=ToolName.ANALYZE_IMAGE,
            description="Look at a drone or camera frame (frame_id from get_fire_data) and answer a question about it, "
                        "for example where the fire front is and whether people are visible.",
            parameters=object_schema({
                "frame_id": {"type": "string", "description": "Frame id from get_fire_data."},
                "question": {"type": "string", "description": "What to look for in the frame."},
            }, ["frame_id", "question"]),
            tier=ToolTier.AGENT_ALONE, roles=background, handler=analyze_image,
        ),
        ToolSpec(
            name=ToolName.PREDICT_SPREAD,
            description="Predict the fire area of a wildfire incident for future time horizons from hotspots and wind "
                        "(simplified demo model). Returns one forecast_id per horizon.",
            parameters=object_schema({
                "incident_id": INCIDENT_ID,
                "horizons_minutes": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 720},
                                     "description": "Forecast horizons in minutes, for example [60, 120, 180]."},
                "initial_radius_m": {"type": "number", "minimum": 10, "maximum": 5000,
                                     "description": "Current fire size as a radius in metres, if known."},
            }, ["incident_id"]),
            tier=ToolTier.AGENT_ALONE, roles=background, handler=predict_spread,
        ),
        ToolSpec(
            name=ToolName.ESTIMATE_EXPOSURE,
            description="List people (sites with estimates), trains and infrastructure (rail lines, roads, power lines) "
                        "inside or near a predicted fire area.",
            parameters=object_schema({"forecast_id": FORECAST_ID}, ["forecast_id"]),
            tier=ToolTier.AGENT_ALONE, roles=background, handler=estimate_exposure,
        ),
        ToolSpec(
            name=ToolName.PLAN_EVACUATION,
            description="Plan the fastest walking route from where people are to an assembly point that is reachable, "
                        "big enough, and keeps a safety distance from the predicted fire area. Use the longest forecast horizon.",
            parameters=object_schema({
                "incident_id": INCIDENT_ID,
                "forecast_id": FORECAST_ID,
                "start_latitude": LATITUDE,
                "start_longitude": LONGITUDE,
                "people_count": {"type": "integer", "minimum": 1, "description": "Number of people to evacuate."},
            }, ["incident_id", "forecast_id", "start_latitude", "start_longitude"]),
            tier=ToolTier.AGENT_ALONE, roles=background, handler=plan_evacuation,
        ),
        ToolSpec(
            name=ToolName.DRAFT_PUBLIC_ALERT,
            description="Propose a public alert on Alertswiss for a predicted fire area, with a headline and an "
                        "instruction per language (the canton's official language is required).",
            parameters=object_schema({
                "incident_id": INCIDENT_ID,
                "forecast_id": FORECAST_ID,
                "alert_kind": enum_schema(PublicAlertKind, "What people must do."),
                "severity": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Severity 1-5."},
                "area_description": {"type": "string", "description": "Alert area in words."},
                "texts": {
                    "type": "array",
                    "minItems": 1,
                    "description": "Alert text per language.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "language": enum_schema(Language, "Language code."),
                            "headline": {"type": "string", "description": "Short headline."},
                            "instruction": {"type": "string", "description": "What people must do now."},
                        },
                        "required": ["language", "headline", "instruction"],
                    },
                },
                "reason": REASON,
            }, ["incident_id", "forecast_id", "alert_kind", "severity", "area_description", "texts", "reason"]),
            tier=ToolTier.OPERATOR_APPROVES, roles=background, handler=draft_public_alert,
        ),
        ToolSpec(
            name=ToolName.REQUEST_INFRA_ACTION,
            description="Propose an infrastructure action in or near the fire area: hold trains on a rail line, close a "
                        "road, or switch off a power line (asset_id from estimate_exposure).",
            parameters=object_schema({
                "incident_id": INCIDENT_ID,
                "asset_id": {"type": "string", "description": "Asset id from estimate_exposure."},
                "action": enum_schema(InfraActionKind, "Action; must fit the asset kind."),
                "reason": REASON,
            }, ["incident_id", "asset_id", "action", "reason"]),
            tier=ToolTier.OPERATOR_APPROVES, roles=background, handler=request_infra_action,
        ),
        ToolSpec(
            name=ToolName.MAKE_ROUTE_CARD,
            description="Draw an evacuation route card (SVG) from a planned route, for phones and the alert page. "
                        "The map is drawn by code from route data.",
            parameters=object_schema({
                "route_id": {"type": "string", "description": "Route id from plan_evacuation."},
                "language": enum_schema(Language, "Language of the labels."),
            }, ["route_id", "language"]),
            tier=ToolTier.AGENT_ALONE, roles=background, handler=make_route_card,
        ),
    ]
