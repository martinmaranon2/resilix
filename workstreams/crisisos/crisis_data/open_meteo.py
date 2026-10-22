"""
Open-Meteo Weather API Integration Client for CrisisOS Switzerland.

This module connects to the Open-Meteo Weather API to retrieve real-time weather
observations, precipitation forecasts, and wind conditions for Zurich and broader Switzerland.
Open-Meteo provides high-resolution European numerical weather forecasts without requiring
an API key for noncommercial emergency intelligence operations.

Use Cases:
1. Fetching current precipitation, rain, wind speed, wind direction, and temperature in Zurich.
2. Obtaining 48-hour short-term rainfall forecasts to anticipate flood risks on the Sihl and Limmat.
3. Normalizing weather data into standard CrisisOS observations suitable for Gemini prompt injection.
4. Handling network errors, API rate limiting, and missing parameters gracefully.
"""

from typing import Any, Optional
import requests

from crisis_data.config import Config
from crisis_data.logger import log_function_call, logger
from crisis_data.models import NormalizedObservation, current_utc_iso


class OpenMeteoClient:
    """Client for querying the Open-Meteo Weather Forecast API."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[int] = None) -> None:
        """
        Initialize the OpenMeteoClient.

        Parameters:
            base_url: Optional override for the Open-Meteo forecast endpoint.
            timeout: Optional HTTP request timeout in seconds.
        """
        self.base_url = base_url or Config.OPEN_METEO_BASE_URL
        self.timeout = timeout or Config.OPEN_METEO_TIMEOUT_SECONDS

    @log_function_call
    def get_weather(
        self,
        latitude: float = Config.ZURICH_LAT,
        longitude: float = Config.ZURICH_LON,
        forecast_days: int = 2
    ) -> dict[str, Any]:
        """
        Retrieve current weather conditions and short-term hourly forecast for a location.

        Parameters:
            latitude: Target latitude in WGS84 decimal degrees (defaults to Zurich 47.3769).
            longitude: Target longitude in WGS84 decimal degrees (defaults to Zurich 8.5417).
            forecast_days: Number of forecast days to retrieve (default 2).

        Returns:
            Dictionary containing raw response metadata, normalized observations, and hourly trends.

        Raises:
            requests.RequestException: If the network request fails or server returns an error code.
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,precipitation,rain,weather_code,wind_speed_10m,wind_direction_10m",
            "hourly": "precipitation,rain,wind_speed_10m,wind_direction_10m,temperature_2m",
            "forecast_days": forecast_days,
            "timezone": "UTC",
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as err:
            logger.warning(f"Open-Meteo weather request failed: {err}")
            return {
                "source": "Open-Meteo",
                "status": "DATA_UNAVAILABLE",
                "is_simulated": True,
                "error": str(err),
                "coordinates": {"latitude": latitude, "longitude": longitude},
                "elevation_m": 408.0,
                "current_weather": {},
                "units": {},
                "total_24h_forecast_precip_mm": 0.0,
                "hourly_forecast_preview": {},
                "normalized_observations": [],
            }

        # Parse current observations
        current = data.get("current", {})
        units = data.get("current_units", {})
        observed_time = current.get("time", current_utc_iso())

        normalized_current = [
            NormalizedObservation(
                source="Open-Meteo",
                type="precipitation",
                station_id=f"open_meteo_{latitude:.4f}_{longitude:.4f}",
                location={"latitude": latitude, "longitude": longitude, "elevation_m": data.get("elevation")},
                measurement={"value": current.get("precipitation", 0.0), "unit": units.get("precipitation", "mm")},
                observed_at=observed_time,
                quality="nominal",
            ),
            NormalizedObservation(
                source="Open-Meteo",
                type="rain",
                station_id=f"open_meteo_{latitude:.4f}_{longitude:.4f}",
                location={"latitude": latitude, "longitude": longitude, "elevation_m": data.get("elevation")},
                measurement={"value": current.get("rain", 0.0), "unit": units.get("rain", "mm")},
                observed_at=observed_time,
                quality="nominal",
            ),
            NormalizedObservation(
                source="Open-Meteo",
                type="wind_speed",
                station_id=f"open_meteo_{latitude:.4f}_{longitude:.4f}",
                location={"latitude": latitude, "longitude": longitude, "elevation_m": data.get("elevation")},
                measurement={"value": current.get("wind_speed_10m", 0.0), "unit": units.get("wind_speed_10m", "km/h")},
                observed_at=observed_time,
                quality="nominal",
            ),
            NormalizedObservation(
                source="Open-Meteo",
                type="temperature",
                station_id=f"open_meteo_{latitude:.4f}_{longitude:.4f}",
                location={"latitude": latitude, "longitude": longitude, "elevation_m": data.get("elevation")},
                measurement={"value": current.get("temperature_2m", 0.0), "unit": units.get("temperature_2m", "°C")},
                observed_at=observed_time,
                quality="nominal",
            ),
        ]

        # Extract hourly forecast summary (next 24 hours precipitation accumulation)
        hourly = data.get("hourly", {})
        precip_series = hourly.get("precipitation", [])[:24]
        total_24h_precip = round(sum(p for p in precip_series if isinstance(p, (int, float))), 2)

        return {
            "source": "Open-Meteo",
            "status": "NOMINAL",
            "is_simulated": False,
            "coordinates": {"latitude": latitude, "longitude": longitude},
            "elevation_m": data.get("elevation"),
            "current_weather": current,
            "units": units,
            "total_24h_forecast_precip_mm": total_24h_precip,
            "hourly_forecast_preview": {
                "time": hourly.get("time", [])[:12],
                "precipitation_mm": hourly.get("precipitation", [])[:12],
                "wind_speed_kmh": hourly.get("wind_speed_10m", [])[:12],
            },
            "normalized_observations": [obs.to_dict() for obs in normalized_current],
        }


# Module singleton instance
_default_client = OpenMeteoClient()


@log_function_call
def get_weather(latitude: float = Config.ZURICH_LAT, longitude: float = Config.ZURICH_LON) -> dict[str, Any]:
    """
    Convenience wrapper to retrieve current weather and short-term forecast.

    Parameters:
        latitude: Target latitude in WGS84 degrees.
        longitude: Target longitude in WGS84 degrees.

    Returns:
        Structured weather data including normalized observations.
    """
    return _default_client.get_weather(latitude=latitude, longitude=longitude)
