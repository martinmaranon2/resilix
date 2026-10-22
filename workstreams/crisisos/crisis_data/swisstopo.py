"""
swisstopo / Swiss Federal Geodata Integration Module for CrisisOS.

This module interfaces with swisstopo geodata APIs (https://docs.geo.admin.ch/),
providing digital elevation queries, coordinate transformations between Swiss LV95
(EPSG:2056) and WGS84 (EPSG:4326), and spatial links to Swiss Federal Geoportal
hazard and hydrological layers.

Use Cases:
1. Converting coordinates between international WGS84 (lat/lon) and official Swiss LV95 (East/North).
2. Fetching precise terrain elevation (m a.s.l.) for any coordinate in Switzerland via swisstopo Height API.
3. Generating Swiss Federal Geoportal (map.geo.admin.ch) deep links with active hazard and flood map layers.
4. Enabling flood vulnerability assessments by comparing river water levels against terrain elevation.
"""

import math
from typing import Any, Optional
import requests

from crisis_data.config import Config
from crisis_data.logger import log_function_call, logger


def wgs84_to_lv95(latitude: float, longitude: float) -> tuple[float, float]:
    """
    Convert WGS84 coordinates (degrees) to Swiss LV95 coordinates (meters) using official formulas.

    Formulas from swisstopo approximate conversion documentation:
    y = Easting (approx 2'600'000 m), x = Northing (approx 1'200'000 m).

    Parameters:
        latitude: WGS84 latitude in decimal degrees (e.g., 47.3769 for Zurich).
        longitude: WGS84 longitude in decimal degrees (e.g., 8.5417 for Zurich).

    Returns:
        Tuple of (easting, northing) in meters (EPSG:2056).
    """
    # Convert latitude / longitude from degrees into seconds
    phi = latitude * 3600.0
    lam = longitude * 3600.0

    # Auxiliary values (difference to Bern reference point in 10000")
    phi_aux = (phi - 169028.66) / 10000.0
    lam_aux = (lam - 26782.5) / 10000.0

    # Calculate Easting (E / y) in LV95 (adds 2,000,000 m offset)
    easting = (
        2600072.37
        + 211455.93 * lam_aux
        - 10938.51 * lam_aux * phi_aux
        - 0.36 * lam_aux * (phi_aux ** 2)
        - 44.54 * (lam_aux ** 3)
    )

    # Calculate Northing (N / x) in LV95 (adds 1,000,000 m offset)
    northing = (
        1200147.07
        + 308807.95 * phi_aux
        + 3745.25 * (lam_aux ** 2)
        + 76.63 * (phi_aux ** 2)
        - 194.56 * (lam_aux ** 2) * phi_aux
        + 119.57 * (phi_aux ** 3)
    )

    return (round(easting, 2), round(northing, 2))


def lv95_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """
    Convert Swiss LV95 coordinates (meters) to WGS84 coordinates (degrees) using official formulas.

    Parameters:
        easting: LV95 East coordinate in meters (EPSG:2056, range ~2,480,000 to 2,840,000).
        northing: LV95 North coordinate in meters (EPSG:2056, range ~1,070,000 to 1,300,000).

    Returns:
        Tuple of (latitude, longitude) in WGS84 decimal degrees.
    """
    y_aux = (easting - 2600000.0) / 1000000.0
    x_aux = (northing - 1200000.0) / 1000000.0

    lam = (
        2.6779094
        + 4.728982 * y_aux
        + 0.791484 * y_aux * x_aux
        + 0.1306 * y_aux * (x_aux ** 2)
        - 0.0436 * (y_aux ** 3)
    )

    phi = (
        16.9023892
        + 3.238272 * x_aux
        - 0.270978 * (y_aux ** 2)
        - 0.002528 * (x_aux ** 2)
        - 0.0447 * (y_aux ** 2) * x_aux
        - 0.0140 * (x_aux ** 3)
    )

    # Convert to decimal degrees
    longitude = lam * 100.0 / 36.0
    latitude = phi * 100.0 / 36.0

    return (round(latitude, 6), round(longitude, 6))


class SwisstopoClient:
    """Client for querying swisstopo REST services and geographic reference layers."""

    def __init__(self, timeout: Optional[int] = None) -> None:
        """
        Initialize the SwisstopoClient.

        Parameters:
            timeout: Optional HTTP request timeout in seconds.
        """
        self.timeout = timeout or Config.SWISSTOPO_TIMEOUT_SECONDS

    @log_function_call
    def get_elevation(self, latitude: float, longitude: float) -> dict[str, Any]:
        """
        Retrieve ground elevation above sea level from the swisstopo Digital Elevation Model.

        Parameters:
            latitude: Target latitude in WGS84 degrees.
            longitude: Target longitude in WGS84 degrees.

        Returns:
            Dictionary with WGS84 coords, LV95 coords, and elevation in meters.
        """
        easting, northing = wgs84_to_lv95(latitude, longitude)
        params = {"easting": str(int(easting)), "northing": str(int(northing))}
        url = Config.SWISSTOPO_HEIGHT_URL

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            height_val = float(data.get("height", 0.0))
            is_simulated = False
            status = "NOMINAL"
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"Failed to query swisstopo elevation: {e}. Using nominal fallback.")
            height_val = 408.0
            is_simulated = True
            status = "DATA_UNAVAILABLE"

        return {
            "source": "swisstopo",
            "status": status,
            "is_simulated": is_simulated,
            "coordinates_wgs84": {"latitude": latitude, "longitude": longitude},
            "coordinates_lv95": {"easting": easting, "northing": northing},
            "elevation_m": height_val,
            "crs": "EPSG:2056 / EPSG:4326",
        }

    @log_function_call
    def get_geoportal_map_url(
        self,
        latitude: float = Config.ZURICH_LAT,
        longitude: float = Config.ZURICH_LON,
        layers: Optional[list[str]] = None
    ) -> str:
        """
        Construct a direct Swiss Federal Geoportal (map.geo.admin.ch) link centered on coordinates.

        Parameters:
            latitude: Latitude in WGS84 degrees.
            longitude: Longitude in WGS84 degrees.
            layers: List of map layer identifiers (e.g. flood or hazard layers).

        Returns:
            Direct URL string opening the official Geoportal map viewer.
        """
        easting, northing = wgs84_to_lv95(latitude, longitude)
        layer_param = ",".join(layers) if layers else "ch.bafu.hydrologie-gewaesserzustandsmessstellen-temperatur"
        url = (
            f"https://map.geo.admin.ch/?lang=en&bgLayer=ch.swisstopo.pixelkarte-farbe"
            f"&E={int(easting)}&N={int(northing)}&zoom=8&layers={layer_param}"
        )
        return url


# Module singleton instance
_default_swisstopo_client = SwisstopoClient()


@log_function_call
def get_elevation(latitude: float, longitude: float) -> dict[str, Any]:
    """
    Convenience wrapper to get elevation in meters for any point in Switzerland.

    Parameters:
        latitude: Latitude in WGS84 degrees.
        longitude: Longitude in WGS84 degrees.

    Returns:
        Dictionary with coordinates and elevation.
    """
    return _default_swisstopo_client.get_elevation(latitude=latitude, longitude=longitude)
