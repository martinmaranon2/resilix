"""
Central configuration for the AlpineGuard tools, simulation and agents.

Architecture
------------
All tunable values live in the ``Config`` class: Gemini model names, file locations,
travel speeds for arrival-time estimates, search radii, the constants of the simplified
fire spread model, and rendering sizes. Tools, agents and the simulated world read these
values instead of hard-coding them (team rule 6 in AGENTS.md). Values that differ per
machine can be set with environment variables.

Use cases
---------
1. Choose the Gemini models (env ``ALPINEGUARD_BACKGROUND_MODEL``, ``ALPINEGUARD_VISION_MODEL``).
2. Point the tools at another scenario folder or artifact folder for a demo.
3. Tune the demo fire spread model and the evacuation walking speed in one place.
"""

import os
import tempfile
from pathlib import Path
from typing import Dict, List

from alpineguard.models.calls import Language
from alpineguard.models.resources import UnitKind

PACKAGE_DIR = Path(__file__).resolve().parent


class Config:
    """Central configuration values for tools, simulation and agents."""

    # --------------------------------------------------------------------------
    # Gemini (models listed by the hackathon API key on 2026-10-10)
    # --------------------------------------------------------------------------
    GEMINI_API_KEY_ENV: str = "GEMINI_API_KEY"
    BACKGROUND_AGENT_MODEL: str = os.getenv("ALPINEGUARD_BACKGROUND_MODEL", "gemini-3.8-flash")
    VISION_MODEL: str = os.getenv("ALPINEGUARD_VISION_MODEL", "gemini-3.8-flash")
    VOICE_AGENT_MODEL: str = os.getenv("ALPINEGUARD_VOICE_MODEL", "gemini-3.8-live")
    VOICE_AUDIO_SAMPLE_RATE: int = 24000  # Live API audio output: 16-bit mono PCM
    BACKGROUND_AGENT_MAX_TURNS: int = 24

    # --------------------------------------------------------------------------
    # Files
    # --------------------------------------------------------------------------
    SCENARIO_DIR: Path = PACKAGE_DIR / "simulation" / "scenarios"
    PROTOCOL_DIR: Path = PACKAGE_DIR / "protocols"
    ARTIFACT_DIR: Path = Path(
        os.getenv("ALPINEGUARD_ARTIFACT_DIR", str(Path(tempfile.gettempdir()) / "alpineguard-artifacts"))
    )

    # --------------------------------------------------------------------------
    # Logging
    # --------------------------------------------------------------------------
    LOG_LEVEL: str = os.getenv("ALPINEGUARD_LOG_LEVEL", "INFO")
    LOG_MAX_VALUE_CHARS: int = 300

    # --------------------------------------------------------------------------
    # Arrival time estimates (straight-line distance x factor, average speed)
    # --------------------------------------------------------------------------
    ROAD_DISTANCE_FACTOR: float = 1.4
    TRAIL_DISTANCE_FACTOR: float = 1.25
    WALKING_DETOUR_FACTOR: float = 1.3
    URBAN_WALKING_SPEED_KMH: float = 5.0
    EVACUATION_WALKING_SPEED_KMH: float = 4.0
    NAISMITH_MINUTES_PER_100M_ASCENT: float = 10.0  # Naismith's rule: 1 hour per 600 m of ascent
    CABLE_CAR_RIDE_MINUTES: float = 8.0
    UNIT_SPEED_KMH: Dict[UnitKind, float] = {
        UnitKind.AMBULANCE: 45.0,
        UnitKind.FIRE_ENGINE: 40.0,
        UnitKind.FIREFIGHTING_HELICOPTER: 200.0,
        UnitKind.POLICE_PATROL: 45.0,
        UnitKind.REGA_HELICOPTER: 220.0,
        UnitKind.FIRST_RESPONDER: 12.0,
        UnitKind.DRONE: 50.0,
    }
    UNIT_TURNOUT_MINUTES: Dict[UnitKind, float] = {
        UnitKind.AMBULANCE: 1.5,
        UnitKind.FIRE_ENGINE: 2.0,
        UnitKind.FIREFIGHTING_HELICOPTER: 15.0,
        UnitKind.POLICE_PATROL: 1.0,
        UnitKind.REGA_HELICOPTER: 4.0,
        UnitKind.FIRST_RESPONDER: 1.0,
        UnitKind.DRONE: 1.0,
    }

    # --------------------------------------------------------------------------
    # Search radii, time windows, result sizes
    # --------------------------------------------------------------------------
    AED_SEARCH_RADIUS_M: float = 1000.0
    FIRST_RESPONDER_RADIUS_M: float = 800.0
    RELATED_INCIDENT_RADIUS_M: float = 2500.0
    RELATED_INCIDENT_WINDOW_MINUTES: int = 30
    FIRE_DATA_RADIUS_KM: float = 5.0
    EXPOSURE_NEAR_DISTANCE_M: float = 500.0
    DEFAULT_MAX_RESULTS: int = 5

    # --------------------------------------------------------------------------
    # Fire spread demo model (ellipse stretched downwind)
    # --------------------------------------------------------------------------
    SPREAD_MODEL_NAME: str = "elliptical_wind_demo_v1"
    SPREAD_MODEL_NOTE: str = (
        "Simplified demo model: an ellipse stretched downwind from the ignition area. "
        "It ignores slope, fuel type, terrain and wind changes. Not validated for operations."
    )
    SPREAD_BASE_RATE_M_PER_MIN: float = 3.0
    SPREAD_WIND_FACTOR_PER_KMH: float = 0.06
    SPREAD_BACKING_FRACTION: float = 0.1
    SPREAD_LENGTH_TO_BREADTH_PER_M_S: float = 0.25
    SPREAD_MAX_LENGTH_TO_BREADTH: float = 4.0
    SPREAD_INITIAL_RADIUS_M: float = 100.0
    SPREAD_POLYGON_POINTS: int = 36
    SPREAD_DEFAULT_HORIZONS_MINUTES: List[int] = [60, 120, 180]
    SPREAD_MAX_HORIZON_MINUTES: int = 720
    SPREAD_HOTSPOT_SEARCH_RADIUS_M: float = 1500.0

    # --------------------------------------------------------------------------
    # Evacuation routing
    # --------------------------------------------------------------------------
    EVACUATION_SAFETY_BUFFER_M: float = 150.0
    EVACUATION_ASCENT_WARNING_M: float = 50.0
    EVACUATION_MAX_ESCAPE_M: float = 400.0  # max distance inside the danger zone when the start is in it
    EVACUATION_ESCAPE_SAMPLE_STEP_M: float = 20.0

    # --------------------------------------------------------------------------
    # Public alerts
    # --------------------------------------------------------------------------
    PUBLIC_ALERT_CHANNEL: str = "Alertswiss (simulated)"
    CANTON_ALERT_LANGUAGES: Dict[str, List[Language]] = {
        "ZH": [Language.DE],
        "UR": [Language.DE],
        "BE": [Language.DE, Language.FR],
        "VS": [Language.DE, Language.FR],
        "GR": [Language.DE, Language.IT],
        "TI": [Language.IT],
        "GE": [Language.FR],
        "VD": [Language.FR],
    }
    DEFAULT_ALERT_LANGUAGES: List[Language] = [Language.DE]

    # --------------------------------------------------------------------------
    # Route card rendering
    # --------------------------------------------------------------------------
    ROUTE_CARD_WIDTH_PX: int = 800
    ROUTE_CARD_HEIGHT_PX: int = 600
    ROUTE_CARD_MARGIN_PX: int = 60
