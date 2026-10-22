"""
Simulated external systems for one demo scenario.

Architecture
------------
``SimulatedWorld`` loads a scenario file (``simulation/scenarios/<id>.json``) into typed
records and plays the role of all external systems: the telephony gateway (calls with
AML position), unit status, AED register, hospitals, satellite hotspots, weather,
drone and camera frames, people at sites, infrastructure, trains and the path network.
Tools only read data through the methods below, and change the world only through the
effect methods, which are called by executors after operator approval.

Data seam for the teammate data layer (``crisis_data`` on branch feat/data-integration):
- ``weather_at``          -> crisis_data.get_weather(lat, lon)               (Open-Meteo)
- ``hospitals``           -> crisis_data.get_nearby_infrastructure(...)      (OSM hospitals)
- ``fire_danger_level``   -> crisis_data.get_hazard_warnings(plz)            (forest fire level)
- ``frames``              -> crisis_data.get_nearby_webcams / get_webcam_image
- ``sites``               -> crisis_data.get_building_exposure / get_population_exposure_metrics
- ``hotspots``, ``aeds``  -> no source yet (satellite fire hotspots; OSM emergency=defibrillator)
A subclass can override these methods with live data; the tools stay the same.

Use cases
---------
1. Run the cardiac arrest and forest fire demos without any external system.
2. Check in tests that nothing changes before an operator approves.
3. Show the operator console what changed after each approval.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Any, Dict, Iterable, List, Optional

from alpineguard.config import Config
from alpineguard.models.alerts import PublicAlertDraft
from alpineguard.models.calls import (
    CentreMessage,
    EmergencyCentre,
    HandoffRequest,
    IncomingCall,
    Language,
    LocationSource,
    SocialPost,
)
from alpineguard.models.domain import Coordinates, SeverityLevel
from alpineguard.models.exposure import (
    ACTION_FOR_ASSET_KIND,
    STATUS_AFTER_ACTION,
    InfraActionKind,
    InfraAsset,
    InfraAssetKind,
    Site,
    SiteKind,
    Train,
    TrainStatus,
)
from alpineguard.models.fire import DetectionConfidence, FireHotspot, ImageFrame, SensorKind, WeatherSnapshot
from alpineguard.models.resources import Aed, Hospital, HospitalCapability, Unit, UnitKind, UnitStatus
from alpineguard.models.routing import AssemblyPoint, PathKind, RoadEdge, RoadNode
from alpineguard.time_utils import parse_iso


def _coords(data: Dict[str, Any]) -> Coordinates:
    return Coordinates(
        latitude=float(data["latitude"]),
        longitude=float(data["longitude"]),
        altitude_m=float(data["altitude_m"]) if data.get("altitude_m") is not None else None,
    )


class SimulatedWorld:
    """All external systems of one demo scenario, in memory."""

    def __init__(self, data: Dict[str, Any], scenario_dir: Path) -> None:
        """
        Build the world from a parsed scenario file.

        Parameters:
            data: Parsed scenario JSON.
            scenario_dir: Folder of the scenario file (for relative image paths).

        Raises:
            KeyError, ValueError: If the scenario file misses fields or has invalid values.
        """
        self.scenario_id: str = data["scenario_id"]
        self.title: str = data["title"]
        self.canton: str = data["canton"]
        self.data_note: str = data.get("data_note", "")
        self.operator_goal: str = data["operator_goal"]
        self.voice_script: List[Dict[str, str]] = list(data.get("voice_script", []))
        self.trigger_call_ids: List[str] = list(
            data.get("trigger_call_ids", [c["call_id"] for c in data.get("calls", [])])
        )
        self._scenario_dir = scenario_dir
        self._clock_start: datetime = parse_iso(data["clock_start"])
        self._loaded_at = monotonic()

        self._calls = [
            IncomingCall(
                call_id=c["call_id"],
                centre=EmergencyCentre(c["centre"]),
                received_at=parse_iso(c["received_at"]),
                language=Language(c["language"]),
                location=_coords(c["location"]),
                location_accuracy_m=float(c["location_accuracy_m"]),
                location_source=LocationSource(c["location_source"]),
                address_hint=c["address_hint"],
                caller_number_masked=c["caller_number_masked"],
                transcript=list(c["transcript"]),
            )
            for c in data.get("calls", [])
        ]
        self._social_posts = [
            SocialPost(
                post_id=p["post_id"],
                platform=p["platform"],
                posted_at=parse_iso(p["posted_at"]),
                text=p["text"],
                location=_coords(p["location"]) if p.get("location") else None,
            )
            for p in data.get("social_posts", [])
        ]
        self._units = [
            Unit(
                unit_id=u["unit_id"],
                name=u["name"],
                kind=UnitKind(u["kind"]),
                centre=EmergencyCentre(u["centre"]),
                location=_coords(u["location"]),
                status=UnitStatus(u["status"]),
            )
            for u in data.get("units", [])
        ]
        self._aeds = [
            Aed(
                aed_id=a["aed_id"],
                name=a["name"],
                location=_coords(a["location"]),
                access_hint=a["access_hint"],
                available_24h=bool(a["available_24h"]),
            )
            for a in data.get("aeds", [])
        ]
        self._hospitals = [
            Hospital(
                hospital_id=h["hospital_id"],
                name=h["name"],
                location=_coords(h["location"]),
                capabilities=[HospitalCapability(c) for c in h["capabilities"]],
            )
            for h in data.get("hospitals", [])
        ]

        fire = data.get("fire") or {}
        self._fire_danger_level: Optional[SeverityLevel] = (
            SeverityLevel(int(fire["danger_level"])) if fire.get("danger_level") is not None else None
        )
        self._hotspots = [
            FireHotspot(
                hotspot_id=h["hotspot_id"],
                location=_coords(h["location"]),
                detected_at=parse_iso(h["detected_at"]),
                confidence=DetectionConfidence(h["confidence"]),
                fire_radiative_power_mw=float(h["fire_radiative_power_mw"]),
                source=h["source"],
            )
            for h in fire.get("hotspots", [])
        ]
        weather = fire.get("weather")
        self._weather: Optional[WeatherSnapshot] = (
            WeatherSnapshot(
                location=_coords(weather["location"]),
                observed_at=parse_iso(weather["observed_at"]),
                wind_speed_kmh=float(weather["wind_speed_kmh"]),
                wind_from_deg=float(weather["wind_from_deg"]),
                gust_kmh=float(weather["gust_kmh"]),
                temperature_c=float(weather["temperature_c"]),
                relative_humidity_pct=float(weather["relative_humidity_pct"]),
                source=weather["source"],
            )
            if weather
            else None
        )
        self._frames = [
            ImageFrame(
                frame_id=f["frame_id"],
                sensor_kind=SensorKind(f["sensor_kind"]),
                sensor_name=f["sensor_name"],
                location=_coords(f["location"]),
                captured_at=parse_iso(f["captured_at"]),
                scripted_observation=f["scripted_observation"],
                image_path=f.get("image_path"),
            )
            for f in fire.get("frames", [])
        ]

        exposure = data.get("exposure") or {}
        self._sites = [
            Site(
                site_id=s["site_id"],
                name=s["name"],
                kind=SiteKind(s["kind"]),
                location=_coords(s["location"]),
                people_estimate=int(s["people_estimate"]),
            )
            for s in exposure.get("sites", [])
        ]
        self._assets = [
            InfraAsset(
                asset_id=a["asset_id"],
                name=a["name"],
                kind=InfraAssetKind(a["kind"]),
                operator=a["operator"],
                path=[_coords(p) for p in a["path"]],
            )
            for a in exposure.get("assets", [])
        ]
        self._trains = [
            Train(
                train_id=t["train_id"],
                service_name=t["service_name"],
                line_asset_id=t["line_asset_id"],
                location=_coords(t["location"]),
                heading_to=t["heading_to"],
                passengers_estimate=int(t["passengers_estimate"]),
            )
            for t in exposure.get("trains", [])
        ]

        paths = data.get("paths") or {}
        self._nodes = {
            n["node_id"]: RoadNode(node_id=n["node_id"], name=n["name"], location=_coords(n["location"]))
            for n in paths.get("nodes", [])
        }
        self._edges = [
            RoadEdge(
                from_node_id=e["from_node_id"],
                to_node_id=e["to_node_id"],
                name=e["name"],
                kind=PathKind(e["kind"]),
                length_m=float(e["length_m"]) if e.get("length_m") is not None else None,
            )
            for e in paths.get("edges", [])
        ]
        for edge in self._edges:
            if edge.from_node_id not in self._nodes or edge.to_node_id not in self._nodes:
                raise ValueError(f"Edge '{edge.name}' refers to an unknown node")
        self._assembly_points = [
            AssemblyPoint(
                point_id=p["point_id"],
                name=p["name"],
                node_id=p["node_id"],
                location=self._nodes[p["node_id"]].location,
                capacity=int(p["capacity"]),
            )
            for p in paths.get("assembly_points", [])
        ]

        self.published_alerts: List[PublicAlertDraft] = []
        self.centre_messages: List[CentreMessage] = []
        self.handoffs: List[HandoffRequest] = []

    @classmethod
    def load(cls, scenario_id: str, scenario_dir: Path = Config.SCENARIO_DIR) -> "SimulatedWorld":
        """
        Load a scenario by id.

        Parameters:
            scenario_id: File name without ".json" in the scenario folder.
            scenario_dir: Folder with scenario files.

        Returns:
            The simulated world.

        Raises:
            FileNotFoundError: If the scenario file does not exist.
        """
        path = scenario_dir / f"{scenario_id}.json"
        with path.open(encoding="utf-8") as handle:
            return cls(json.load(handle), scenario_dir)

    @staticmethod
    def available_scenarios(scenario_dir: Path = Config.SCENARIO_DIR) -> List[str]:
        """
        List scenario ids in a folder.

        Parameters:
            scenario_dir: Folder with scenario files.

        Returns:
            Sorted scenario ids.
        """
        return sorted(p.stem for p in scenario_dir.glob("*.json"))

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------
    def now(self) -> datetime:
        """
        Current scenario time: scenario start plus real time since loading.

        Returns:
            Timezone-aware scenario time.
        """
        return self._clock_start + timedelta(seconds=monotonic() - self._loaded_at)

    # ------------------------------------------------------------------
    # Data access (the data seam)
    # ------------------------------------------------------------------
    def calls(self) -> List[IncomingCall]:
        """Return all calls of the scenario."""
        return list(self._calls)

    def find_call(self, call_id: str) -> Optional[IncomingCall]:
        """Return the call with this id, or None."""
        return next((c for c in self._calls if c.call_id == call_id), None)

    def social_posts(self) -> List[SocialPost]:
        """Return all social media posts of the scenario."""
        return list(self._social_posts)

    def units(
        self, kinds: Optional[Iterable[UnitKind]] = None, statuses: Optional[Iterable[UnitStatus]] = None
    ) -> List[Unit]:
        """
        Return units, optionally filtered.

        Parameters:
            kinds: Only these unit kinds, if given.
            statuses: Only these statuses, if given.

        Returns:
            Matching units.
        """
        kind_set = set(kinds) if kinds else None
        status_set = set(statuses) if statuses else None
        return [
            u for u in self._units
            if (kind_set is None or u.kind in kind_set) and (status_set is None or u.status in status_set)
        ]

    def find_unit(self, unit_id: str) -> Optional[Unit]:
        """Return the unit with this id, or None."""
        return next((u for u in self._units if u.unit_id == unit_id), None)

    def aeds(self) -> List[Aed]:
        """Return all AEDs of the scenario."""
        return list(self._aeds)

    def hospitals(self) -> List[Hospital]:
        """Return all hospitals of the scenario."""
        return list(self._hospitals)

    def hotspots(self) -> List[FireHotspot]:
        """Return all satellite fire hotspots of the scenario."""
        return list(self._hotspots)

    def fire_danger_level(self) -> Optional[SeverityLevel]:
        """Return the official forest fire danger level (1-5), or None."""
        return self._fire_danger_level

    def weather_at(self, location: Coordinates) -> Optional[WeatherSnapshot]:
        """
        Return the weather for a position.

        Parameters:
            location: Position of interest (the scenario has one weather record).

        Returns:
            Weather snapshot, or None when the scenario has no weather data.
        """
        return self._weather

    def frames(self) -> List[ImageFrame]:
        """Return all drone and camera frames of the scenario."""
        return list(self._frames)

    def find_frame(self, frame_id: str) -> Optional[ImageFrame]:
        """Return the frame with this id, or None."""
        return next((f for f in self._frames if f.frame_id == frame_id), None)

    def resolve_image_path(self, frame: ImageFrame) -> Optional[Path]:
        """
        Resolve a frame's image file relative to the scenario folder.

        Parameters:
            frame: Frame with optional image path.

        Returns:
            Existing file path, or None.
        """
        if not frame.image_path:
            return None
        path = Path(frame.image_path)
        if not path.is_absolute():
            path = self._scenario_dir / path
        return path if path.is_file() else None

    def sites(self) -> List[Site]:
        """Return all places with people."""
        return list(self._sites)

    def assets(self) -> List[InfraAsset]:
        """Return all infrastructure assets."""
        return list(self._assets)

    def find_asset(self, asset_id: str) -> Optional[InfraAsset]:
        """Return the asset with this id, or None."""
        return next((a for a in self._assets if a.asset_id == asset_id), None)

    def trains(self) -> List[Train]:
        """Return all trains."""
        return list(self._trains)

    def road_nodes(self) -> Dict[str, RoadNode]:
        """Return the path network nodes by id."""
        return dict(self._nodes)

    def road_edges(self) -> List[RoadEdge]:
        """Return the path network edges."""
        return list(self._edges)

    def assembly_points(self) -> List[AssemblyPoint]:
        """Return the assembly points."""
        return list(self._assembly_points)

    # ------------------------------------------------------------------
    # Effects (called by executors after operator approval, or by record tools)
    # ------------------------------------------------------------------
    def _available_units(self, unit_ids: List[str]) -> List[Unit]:
        units: List[Unit] = []
        for unit_id in unit_ids:
            unit = self.find_unit(unit_id)
            if unit is None:
                raise ValueError(f"Unknown unit '{unit_id}'")
            if unit.status != UnitStatus.AVAILABLE:
                raise ValueError(f"Unit '{unit_id}' is not available (status: {unit.status.value})")
            units.append(unit)
        return units

    def dispatch_units(self, unit_ids: List[str], incident_id: str) -> List[Unit]:
        """
        Send units to an incident (all or none).

        Parameters:
            unit_ids: Units to send.
            incident_id: Target incident.

        Returns:
            The dispatched units.

        Raises:
            ValueError: If a unit is unknown or not available; then no unit changes.
        """
        units = self._available_units(unit_ids)
        for unit in units:
            unit.status = UnitStatus.DISPATCHED
            unit.assigned_incident_id = incident_id
        return units

    def alert_responders(self, unit_ids: List[str], incident_id: str) -> List[Unit]:
        """
        Alert volunteer first responders (all or none).

        Parameters:
            unit_ids: First responder units to alert.
            incident_id: Target incident.

        Returns:
            The alerted units.

        Raises:
            ValueError: If a unit is unknown, not available or not a first responder.
        """
        units = self._available_units(unit_ids)
        for unit in units:
            if unit.kind != UnitKind.FIRST_RESPONDER:
                raise ValueError(f"Unit '{unit.unit_id}' is not a first responder")
        for unit in units:
            unit.status = UnitStatus.ALERTED
            unit.assigned_incident_id = incident_id
        return units

    def apply_infra_action(self, asset_id: str, action: InfraActionKind) -> Dict[str, Any]:
        """
        Apply an approved infrastructure action.

        Parameters:
            asset_id: Asset to change.
            action: Action that fits the asset kind.

        Returns:
            New asset status and the ids of held trains.

        Raises:
            ValueError: If the asset is unknown or the action does not fit its kind.
        """
        asset = self.find_asset(asset_id)
        if asset is None:
            raise ValueError(f"Unknown asset '{asset_id}'")
        if ACTION_FOR_ASSET_KIND[asset.kind] != action:
            raise ValueError(f"Action '{action.value}' does not fit asset kind '{asset.kind.value}'")
        asset.status = STATUS_AFTER_ACTION[action]
        held: List[str] = []
        if action == InfraActionKind.HOLD_TRAINS:
            for train in self._trains:
                if train.line_asset_id == asset_id and train.status == TrainStatus.RUNNING:
                    train.status = TrainStatus.HELD
                    held.append(train.train_id)
        return {"asset_id": asset_id, "asset_status": asset.status.value, "held_train_ids": held}

    def publish_alert(self, alert: PublicAlertDraft) -> None:
        """
        Record a published public alert (simulated channel).

        Parameters:
            alert: Alert that the operator approved.
        """
        self.published_alerts.append(alert)

    def deliver_centre_message(self, message: CentreMessage) -> None:
        """
        Deliver information to another emergency centre (simulated inbox).

        Parameters:
            message: Message to deliver.
        """
        self.centre_messages.append(message)

    def record_handoff(self, handoff: HandoffRequest) -> None:
        """
        Put a hand-off request in the operator queue.

        Parameters:
            handoff: Hand-off request.
        """
        self.handoffs.append(handoff)
