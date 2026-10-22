"""
MeteoSwiss Automatic Weather Station (SwissMetNet) STAC & CSV Integration for CrisisOS.

This module retrieves observational ground station data from MeteoSwiss (SwissMetNet / SMN)
via the Swiss Federal Spatial Data Infrastructure STAC catalog
(https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-smn).
It downloads recent 10-minute ground station observations (temperature, precipitation, wind)
for monitoring stations around Zurich (such as SMA - Zürich/Fluntern).

Use Cases:
1. Discovering official SwissMetNet weather stations near Zurich.
2. Fetching real-time 10-minute ground truth observations (precipitation rre150z0, temperature tre200s0, wind).
3. Comparing Open-Meteo forecasts against official ground-truth observations.
4. Normalizing MeteoSwiss records into standard CrisisOS observations with freshness metadata.
"""

import csv
from datetime import datetime, timezone
import io
import math
from typing import Any, Optional
import requests

from crisis_data.config import Config
from crisis_data.logger import log_function_call, logger
from crisis_data.models import NormalizedObservation, current_utc_iso


class MeteoSwissSMNClient:
    """Client for retrieving MeteoSwiss SwissMetNet observations from STAC and CSV assets."""

    KNOWN_ZURICH_STATIONS = {
        "sma": {"id": "sma", "name": "Zürich / Fluntern (SMA)", "latitude": 47.381003, "longitude": 8.567194, "elevation_m": 556},
        "reh": {"id": "reh", "name": "Zürich / Affoltern (REH)", "latitude": 47.427878, "longitude": 8.514336, "elevation_m": 443},
        "klo": {"id": "klo", "name": "Zürich / Kloten (KLO)", "latitude": 47.479533, "longitude": 8.536108, "elevation_m": 427},
    }

    def __init__(self, timeout: Optional[int] = None) -> None:
        """
        Initialize the MeteoSwissSMNClient.

        Parameters:
            timeout: Optional HTTP request timeout in seconds.
        """
        self.timeout = timeout or Config.METEOSWISS_SMN_TIMEOUT_SECONDS

    @log_function_call
    def get_weather_stations(
        self,
        latitude: float = Config.ZURICH_LAT,
        longitude: float = Config.ZURICH_LON,
        radius_km: float = 25.0
    ) -> list[dict[str, Any]]:
        """
        Retrieve SwissMetNet weather stations within a given radius of coordinates.

        Parameters:
            latitude: Center latitude in WGS84 degrees.
            longitude: Center longitude in WGS84 degrees.
            radius_km: Search radius in kilometers.

        Returns:
            List of matching station metadata dictionaries.
        """
        # Calculate great-circle distance
        def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            r = 6371.0
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlam = math.radians(lon2 - lon1)
            a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
            return r * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

        nearby: list[dict[str, Any]] = []
        for station_id, info in self.KNOWN_ZURICH_STATIONS.items():
            dist = haversine_km(latitude, longitude, info["latitude"], info["longitude"])
            if dist <= radius_km:
                station_dict = dict(info)
                station_dict["distance_km"] = round(dist, 2)
                nearby.append(station_dict)

        return sorted(nearby, key=lambda s: s["distance_km"])

    @log_function_call
    def get_station_latest_observations(self, station_id: str = "sma") -> dict[str, Any]:
        """
        Download and parse the latest 10-minute observation from the station's _t_now.csv asset.

        Parameters:
            station_id: MeteoSwiss station code (e.g. 'sma' for Zurich Fluntern).

        Returns:
            Dictionary containing latest observations and normalized CrisisOS records.
        """
        station_id_lower = station_id.lower()
        asset_url = f"{Config.METEOSWISS_SMN_ASSET_BASE}/{station_id_lower}/ogd-smn_{station_id_lower}_t_now.csv"

        station_meta = self.KNOWN_ZURICH_STATIONS.get(station_id_lower, {
            "latitude": Config.ZURICH_LAT,
            "longitude": Config.ZURICH_LON,
            "elevation_m": 450,
            "name": f"Station {station_id}",
        })

        try:
            response = requests.get(asset_url, timeout=self.timeout)
            response.raise_for_status()

            # Parse CSV with semicolon delimiter
            content = response.content.decode("utf-8", errors="replace")
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            if len(lines) < 2:
                raise ValueError(f"No observation data rows in asset for station {station_id}")

            reader = csv.DictReader(lines, delimiter=";")
            rows = list(reader)
            if not rows:
                raise ValueError(f"Empty data rows in CSV for station {station_id}")

            latest_row = rows[-1]  # Most recent 10-minute record
            ref_timestamp = latest_row.get("reference_timestamp", "")
            is_simulated = False
            status = "NOMINAL"
        except (requests.RequestException, ValueError) as err:
            logger.warning(f"Failed to fetch or parse MeteoSwiss SMN data for {station_id}: {err}")
            return {
                "source": "MeteoSwiss",
                "status": "DATA_UNAVAILABLE",
                "is_simulated": True,
                "error": str(err),
                "station": station_meta,
                "timestamp": current_utc_iso(),
                "raw_measurements": {},
                "normalized_observations": [],
                "retrieved_at": current_utc_iso(),
            }

        # Key parameters according to MeteoSwiss SwissMetNet documentation:
        # tre200s0: Air temperature 2 m above ground (°C)
        # ure200s0: Relative humidity 2 m (%)
        # rre150z0: Precipitation amount (mm)
        # fkl010z0: Mean wind speed 10 m (m/s)
        # dkl010z0: Wind direction 10 m (°)
        # prestas0: Station pressure (hPa)

        def safe_float(v: Optional[str]) -> Optional[float]:
            try:
                return float(v) if v is not None and v != "" else None
            except ValueError:
                return None

        temp = safe_float(latest_row.get("tre200s0"))
        humidity = safe_float(latest_row.get("ure200s0"))
        precip = safe_float(latest_row.get("rre150z0"))
        wind_speed_ms = safe_float(latest_row.get("fkl010z0"))
        wind_dir = safe_float(latest_row.get("dkl010z0"))

        normalized: list[dict[str, Any]] = []
        loc = {
            "latitude": station_meta.get("latitude"),
            "longitude": station_meta.get("longitude"),
            "elevation_m": station_meta.get("elevation_m"),
        }

        if temp is not None:
            normalized.append(NormalizedObservation(
                source="MeteoSwiss",
                type="temperature",
                station_id=station_id_lower,
                location=loc,
                measurement={"value": temp, "unit": "°C"},
                observed_at=ref_timestamp,
            ).to_dict())

        if precip is not None:
            normalized.append(NormalizedObservation(
                source="MeteoSwiss",
                type="precipitation",
                station_id=station_id_lower,
                location=loc,
                measurement={"value": precip, "unit": "mm/10min"},
                observed_at=ref_timestamp,
            ).to_dict())

        if wind_speed_ms is not None:
            # Also convert m/s to km/h for convenience
            wind_kmh = round(wind_speed_ms * 3.6, 2)
            normalized.append(NormalizedObservation(
                source="MeteoSwiss",
                type="wind_speed",
                station_id=station_id_lower,
                location=loc,
                measurement={"value": wind_kmh, "unit": "km/h", "raw_ms": wind_speed_ms},
                observed_at=ref_timestamp,
            ).to_dict())

        return {
            "source": "MeteoSwiss",
            "status": "NOMINAL",
            "is_simulated": False,
            "station": station_meta,
            "timestamp": ref_timestamp,
            "raw_measurements": {
                "temperature_c": temp,
                "humidity_percent": humidity,
                "precipitation_10min_mm": precip,
                "wind_speed_ms": wind_speed_ms,
                "wind_direction_deg": wind_dir,
            },
            "normalized_observations": normalized,
            "retrieved_at": current_utc_iso(),
        }


# Module singleton instance
_default_meteoswiss_smn_client = MeteoSwissSMNClient()


@log_function_call
def get_weather_stations(
    latitude: float = Config.ZURICH_LAT,
    longitude: float = Config.ZURICH_LON,
    radius_km: float = 25.0
) -> list[dict[str, Any]]:
    """
    Convenience wrapper to locate nearby MeteoSwiss stations.

    Parameters:
        latitude: Target latitude in WGS84 degrees.
        longitude: Target longitude in WGS84 degrees.
        radius_km: Radius in kilometers.

    Returns:
        List of station dictionaries.
    """
    return _default_meteoswiss_smn_client.get_weather_stations(latitude=latitude, longitude=longitude, radius_km=radius_km)


@log_function_call
def get_meteoswiss_observation(station_id: str = "sma") -> dict[str, Any]:
    """
    Convenience wrapper to get recent real observations for a MeteoSwiss station.

    Parameters:
        station_id: Station code (defaults to 'sma' for Zurich Fluntern).

    Returns:
        Dictionary with observation values and normalized records.
    """
    return _default_meteoswiss_smn_client.get_station_latest_observations(station_id=station_id)
