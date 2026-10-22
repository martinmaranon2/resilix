"""
Swiss Flood Hazard Maps Integration (BAFU Aquaprotect) for CrisisOS Switzerland.

This module queries official Swiss Federal Office for the Environment (BAFU / FOEN)
flood hazard maps via the Federal Spatial Data Infrastructure (geo.admin.ch) WMS service.
The Aquaprotect models (`ch.bafu.aquaprotect_050`, `ch.bafu.aquaprotect_100`, `ch.bafu.aquaprotect_250`,
`ch.bafu.aquaprotect_500`) delineate inundation zones for flood return periods of 50, 100, 250, and 500 years.

During hydrological crises in Zurich, comparing real-time river gauge levels on the Sihl and Limmat
against the static 100-year flood zone allows CrisisOS to automatically detect which streets,
bridges, and critical infrastructure facilities are situated directly within dangerous flood plains.

Use Cases:
1. Determining whether a specific coordinate (e.g. Zurich Central, Hardbrücke, Sihlhölzli) lies within the 100-year flood hazard zone.
2. Generating direct Web Map Service (WMS) overlay tiles for visual display in the frontend or visual analysis.
3. Providing deep-links to the Swiss Federal Geoportal (map.geo.admin.ch) with active flood hazard layer presets.
"""

from typing import Any, Optional
import requests

from crisis_data.config import Config
from crisis_data.logger import log_function_call, logger
from crisis_data.models import FloodHazardInfo
from crisis_data.swisstopo import wgs84_to_lv95


class FloodHazardClient:
    """Client for evaluating Swiss flood hazard zones via geo.admin.ch WMS."""

    def __init__(self, timeout_seconds: Optional[int] = None) -> None:
        """
        Initialize the flood hazard client.

        Args:
            timeout_seconds: Request timeout in seconds.
        """
        self.timeout: int = timeout_seconds or Config.FLOOD_HAZARD_TIMEOUT_SECONDS
        self.wms_base_url: str = Config.BAFU_WMS_URL

    @log_function_call
    def check_flood_hazard(
        self,
        latitude: float = Config.ZURICH_LAT,
        longitude: float = Config.ZURICH_LON,
        return_period: int = 100,
    ) -> dict[str, Any]:
        """
        Check whether given WGS84 coordinates fall inside a BAFU Aquaprotect flood risk zone.

        Args:
            latitude: Latitude in WGS84 (default: Zurich 47.3769).
            longitude: Longitude in WGS84 (default: Zurich 8.5417).
            return_period: Return period in years (50, 100, 250, 500). Defaults to 100.

        Returns:
            Dictionary containing flood hazard assessment, risk level, and map links.
        """
        # Determine appropriate layer ID
        layer_map = {
            50: Config.BAFU_AQUAPROTECT_LAYER_50,
            100: Config.BAFU_AQUAPROTECT_LAYER_100,
            250: Config.BAFU_AQUAPROTECT_LAYER_250,
            500: Config.BAFU_AQUAPROTECT_LAYER_500,
        }
        layer_id = layer_map.get(return_period, Config.BAFU_AQUAPROTECT_LAYER_100)

        # Convert WGS84 to Swiss LV95 (EPSG:2056)
        east, north = wgs84_to_lv95(latitude, longitude)

        # Construct small bounding box centered around the point
        buffer_m = 500.0
        min_e = east - buffer_m
        max_e = east + buffer_m
        min_n = north - buffer_m
        max_n = north + buffer_m
        bbox_str = f"{min_e:.0f},{min_n:.0f},{max_e:.0f},{max_n:.0f}"

        # Standard WMS 1.3.0 GetFeatureInfo in EPSG:2056
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetFeatureInfo",
            "LAYERS": layer_id,
            "QUERY_LAYERS": layer_id,
            "CRS": "EPSG:2056",
            "BBOX": bbox_str,
            "WIDTH": "500",
            "HEIGHT": "500",
            "I": "250",
            "J": "250",
            "INFO_FORMAT": "application/json",
        }

        is_in_flood_zone = False
        data_available = True
        status_msg = "NOMINAL"
        try:
            response = requests.get(
                self.wms_base_url,
                params=params,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                try:
                    data = response.json()
                    features = data.get("features", [])
                    if len(features) > 0:
                        is_in_flood_zone = True
                except ValueError as json_err:
                    logger.warning(f"Failed to parse WMS response as JSON: {json_err}")
                    data_available = False
                    status_msg = f"INVALID_JSON: {json_err}"
            else:
                logger.warning(
                    f"WMS flood hazard query returned non-200 status {response.status_code}"
                )
                data_available = False
                status_msg = f"HTTP_ERROR_{response.status_code}"
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to query WMS flood hazard zone: {e}")
            data_available = False
            status_msg = f"NETWORK_ERROR: {e}"

        # Assess qualitative risk
        if not data_available:
            risk_level = "UNKNOWN"
        elif is_in_flood_zone:
            if return_period <= 50:
                risk_level = "HIGH"
            elif return_period <= 100:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"
        else:
            risk_level = "NONE"

        # Construct Geoportal and WMS overlay URLs
        geoportal_url = f"https://map.geo.admin.ch/?layers={layer_id}&E={east:.1f}&N={north:.1f}&zoom=8"
        wms_overlay_url = (
            f"{self.wms_base_url}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap"
            f"&LAYERS={layer_id}&CRS=EPSG:2056&BBOX={bbox_str}&WIDTH=800&HEIGHT=600&FORMAT=image/png&TRANSPARENT=TRUE"
        )

        hazard_info = FloodHazardInfo(
            latitude=latitude,
            longitude=longitude,
            lv95_east=round(east, 2),
            lv95_north=round(north, 2),
            is_in_flood_zone=is_in_flood_zone,
            return_period_years=return_period,
            risk_level=risk_level,
            layer_name=layer_id,
            geoportal_url=geoportal_url,
            wms_overlay_url=wms_overlay_url,
            source="BAFU_Aquaprotect",
            data_available=data_available,
            status=status_msg,
        )

        return hazard_info.to_dict()


# Default client instance
_default_flood_client = FloodHazardClient()


@log_function_call
def check_flood_hazard(
    latitude: float = Config.ZURICH_LAT,
    longitude: float = Config.ZURICH_LON,
    return_period: int = 100,
) -> dict[str, Any]:
    """
    Public entry point to assess flood risk zone occupancy for a location.

    Args:
        latitude: WGS84 latitude.
        longitude: WGS84 longitude.
        return_period: Return period in years (50, 100, 250, 500).

    Returns:
        Flood hazard dictionary with risk assessment and geoportal links.
    """
    return _default_flood_client.check_flood_hazard(
        latitude=latitude,
        longitude=longitude,
        return_period=return_period,
    )
