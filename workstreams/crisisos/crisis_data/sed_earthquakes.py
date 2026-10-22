"""
Swiss Seismological Service (SED at ETH Zurich) Integration for CrisisOS Switzerland.

This module connects to the official FDSN (International Federation of Digital Seismograph Networks)
event query service operated by the Swiss Seismological Service (Schweizerischer Erdbebendienst, SED)
at ETH Zurich (http://www.seismo.ethz.ch/).

Earthquakes and seismic tremors can trigger secondary environmental hazards in Switzerland,
including dam instability, landslides, rockfalls into river valleys, and sudden water surges.
By integrating live seismic events, CrisisOS can cross-correlate sudden river gauge fluctuations
or infrastructure damages with recent seismic activity.

Use Cases:
1. Detecting recent earthquakes and seismic events within Switzerland and neighboring alpine regions.
2. Filtering events by minimum magnitude (e.g. M >= 1.0) and geographic proximity.
3. Supplying magnitude, focal depth, event type (natural earthquake vs quarry blast), and timestamps to Gemini.
4. Providing real-time event status and catalog freshness.
5. Providing explicit DATA_UNAVAILABLE status flags and simulated fallback events during network or SED outages.
"""

from datetime import datetime, timezone
from typing import Any, Optional
import requests

from crisis_data.config import Config
from crisis_data.logger import log_function_call, logger
from crisis_data.models import EarthquakeEvent


class SedEarthquakeClient:
    """Client for retrieving seismic event data from the ETH Swiss Seismological Service."""

    def __init__(self, timeout_seconds: Optional[int] = None) -> None:
        """
        Initialize the SED earthquake client.

        Args:
            timeout_seconds: Request timeout in seconds.
        """
        self.timeout: int = timeout_seconds or Config.SED_TIMEOUT_SECONDS
        self.endpoint: str = Config.SED_FDSN_URL
        self.last_fetch_success: bool = True
        self.last_fetch_error: Optional[str] = None

    @log_function_call
    def get_recent_earthquakes(
        self,
        min_magnitude: float = Config.SED_DEFAULT_MIN_MAGNITUDE,
        limit: int = 15,
        swiss_only: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Retrieve recent seismic events from the SED FDSN web service.

        Args:
            min_magnitude: Minimum magnitude threshold (e.g. 0.5 or 1.0).
            limit: Maximum number of events to return.
            swiss_only: If True, restricts query to the Swiss national bounding box.

        Returns:
            List of normalized earthquake event dictionaries.
        """
        params: dict[str, Any] = {
            "format": "text",
            "minmagnitude": min_magnitude,
            "limit": limit,
        }

        if swiss_only:
            # Swiss national bounding box
            params["minlatitude"] = 45.80
            params["maxlatitude"] = 47.85
            params["minlongitude"] = 5.95
            params["maxlongitude"] = 10.50

        events: list[dict[str, Any]] = []
        self.last_fetch_success = False
        self.last_fetch_error = None
        try:
            response = requests.get(
                self.endpoint,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            events = self._parse_fdsn_text(response.text)
            self.last_fetch_success = True
        except requests.exceptions.RequestException as e:
            self.last_fetch_success = False
            self.last_fetch_error = str(e)
            logger.error(f"Error retrieving earthquakes from SED ETHZ: {e}")
            fallback_event = EarthquakeEvent(
                event_id="sed-error-fallback",
                timestamp=datetime.now(timezone.utc).isoformat(),
                latitude=Config.ZURICH_LAT,
                longitude=Config.ZURICH_LON,
                depth_km=0.0,
                magnitude=0.0,
                magnitude_type="ML",
                location_name="SED Data Service Unavailable (Fallback)",
                event_type="service_unavailable",
                source="SED_ETHZ",
                is_simulated=True,
            )
            return [fallback_event.to_dict()]

        return events

    def _parse_fdsn_text(self, text: str) -> list[dict[str, Any]]:
        """
        Parse pipe-delimited FDSN text into normalized EarthquakeEvent records.

        FDSN Header format:
        #EventID|Time|Latitude|Longitude|Depth/km|Author|Catalog|Contributor|ContributorID|MagType|Magnitude|MagAuthor|EventLocationName|EventType

        Args:
            text: Raw FDSN text payload.

        Returns:
            List of normalized earthquake event dictionaries.
        """
        events: list[dict[str, Any]] = []
        lines = text.strip().splitlines()

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("|")
            if len(parts) < 14:
                continue

            try:
                event_id = parts[0]
                timestamp = parts[1]
                lat = float(parts[2])
                lon = float(parts[3])
                depth = float(parts[4])
                mag_type = parts[9]
                mag = float(parts[10])
                location_name = parts[12].strip()
                event_type = parts[13].strip()

                event = EarthquakeEvent(
                    event_id=event_id,
                    timestamp=timestamp,
                    latitude=lat,
                    longitude=lon,
                    depth_km=round(depth, 1),
                    magnitude=round(mag, 2),
                    magnitude_type=mag_type,
                    location_name=location_name,
                    event_type=event_type,
                    source="SED_ETHZ",
                    is_simulated=False,
                )
                events.append(event.to_dict())
            except (ValueError, IndexError) as pe:
                logger.debug(f"Skipping malformed FDSN line: {pe}")

        return events

    @log_function_call
    def get_earthquake_summary(self) -> dict[str, Any]:
        """
        Generate a concise summary of recent seismic activity in Switzerland.

        Returns:
            Summary dictionary with total events, max magnitude, status, and latest event details.
        """
        events = self.get_recent_earthquakes(min_magnitude=0.5, limit=10, swiss_only=True)

        if not self.last_fetch_success:
            return {
                "status": "DATA_UNAVAILABLE",
                "is_simulated": True,
                "data_available": False,
                "error": self.last_fetch_error,
                "has_recent_activity": None,
                "total_events_retrieved": 0,
                "max_magnitude": None,
                "max_magnitude_description": "Data Unavailable",
                "latest_event": None,
                "events": events,
                "sed_portal": "http://www.seismo.ethz.ch",
            }

        max_mag = max([e["magnitude"] for e in events], default=0.0)
        latest = events[0] if events else None

        return {
            "status": "NOMINAL",
            "is_simulated": False,
            "data_available": True,
            "has_recent_activity": len(events) > 0,
            "total_events_retrieved": len(events),
            "max_magnitude": max_mag,
            "max_magnitude_description": f"M{max_mag}" if events else "No events",
            "latest_event": latest,
            "events": events,
            "sed_portal": "http://www.seismo.ethz.ch",
        }


# Default client instance
_default_sed_client = SedEarthquakeClient()


@log_function_call
def get_recent_earthquakes(
    min_magnitude: float = Config.SED_DEFAULT_MIN_MAGNITUDE,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """
    Public entry point to retrieve recent earthquakes in and around Switzerland.

    Args:
        min_magnitude: Minimum magnitude threshold.
        limit: Maximum number of events to fetch.

    Returns:
        List of normalized earthquake records.
    """
    return _default_sed_client.get_recent_earthquakes(
        min_magnitude=min_magnitude,
        limit=limit,
    )


@log_function_call
def get_earthquake_summary() -> dict[str, Any]:
    """
    Public entry point to generate a seismic summary for emergency coordination.

    Returns:
        Summary dictionary with recent seismic events and max magnitude.
    """
    return _default_sed_client.get_earthquake_summary()
