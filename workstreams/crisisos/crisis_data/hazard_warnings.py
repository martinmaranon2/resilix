"""
Official Swiss Natural Hazard Warnings Integration for CrisisOS Switzerland.

This module retrieves live federal natural hazard alerts, meteorological warnings,
and hydrological danger levels from the joint Swiss Federal Natural Hazards platform
(natural-hazards.ch / MeteoSwiss / FOEN / SLF / SED backend).

In emergency coordination, early warning alerts issued by federal authorities
provide critical operational context for CrisisOS. For instance, an active Level 3 or 4
rain or flood alert triggers preemptive monitoring of river levels, automated camera surveillance,
and simulated civil defense preparedness before cresting occurs.

Use Cases:
1. Monitoring active warnings (flood, torrential rain, storm, heat, forest fire) for Zurich postal codes (e.g. 8001, 8005).
2. Extracting warning danger levels (Level 1 = Low to Level 5 = Very Severe) and authoritative advice texts.
3. Supplying official warnings directly to the Gemini reasoning agent to contextualize sensor readings.
4. Linking directly to official guidance on natural-hazards.ch.
"""

from datetime import datetime, timezone
from typing import Any, Optional
import requests

from crisis_data.config import Config
from crisis_data.logger import log_function_call, logger
from crisis_data.models import HazardWarning


# Official Swiss warning type mapping
WARN_TYPE_NAMES: dict[int, str] = {
    1: "Wind / Gale",
    2: "Thunderstorm",
    3: "Heavy Rain",
    4: "Snowfall",
    5: "Icy Roads / Black Ice",
    6: "Frost",
    7: "Fog",
    8: "Heat Wave",
    9: "Drought",
    10: "Forest Fire",
    11: "Flood",
    12: "Earthquake",
}

# Qualitative danger descriptions
WARN_LEVEL_DESCRIPTIONS: dict[int, str] = {
    1: "No or minor danger",
    2: "Moderate danger",
    3: "Significant danger",
    4: "Severe danger",
    5: "Very severe danger",
}


class HazardWarningsClient:
    """Client for retrieving natural hazard warnings from the Swiss federal alerting system."""

    def __init__(self, timeout_seconds: Optional[int] = None) -> None:
        """
        Initialize the hazard warnings client.

        Args:
            timeout_seconds: Request timeout in seconds.
        """
        self.timeout: int = timeout_seconds or Config.NATURAL_HAZARDS_TIMEOUT_SECONDS
        self.endpoint: str = Config.NATURAL_HAZARDS_PLZ_ENDPOINT
        self.last_fetch_success: bool = True
        self.last_fetch_error: Optional[str] = None

    @log_function_call
    def get_hazard_warnings(self, plz: str = Config.DEFAULT_ZURICH_PLZ) -> list[dict[str, Any]]:
        """
        Retrieve all active natural hazard warnings for a Swiss postal code (PLZ).

        Args:
            plz: Swiss 6-digit postal code format (e.g. '800100' for Zurich 8001).

        Returns:
            List of normalized hazard warning dictionaries.
        """
        # Ensure 6-digit PLZ string
        clean_plz = plz.strip()
        if len(clean_plz) == 4:
            clean_plz = f"{clean_plz}00"

        params = {"plz": clean_plz}
        headers = {
            "User-Agent": "CrisisOS-Zurich/1.0 (hackathon-emergency-agent)",
            "Accept": "application/json",
        }

        warnings_list: list[dict[str, Any]] = []
        self.last_fetch_success = False
        self.last_fetch_error = None
        try:
            response = requests.get(
                self.endpoint,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            raw_warnings = data.get("warnings", [])

            for w in raw_warnings:
                w_type = w.get("warnType", 0)
                w_level = w.get("warnLevel", 1)
                type_name = WARN_TYPE_NAMES.get(w_type, f"Unknown Hazard ({w_type})")
                reg_id = w.get("regionId", 0)
                text = w.get("text") or w.get("htmlText") or "No detailed description available."

                # Convert millisecond timestamp to ISO string
                valid_from_ms = w.get("validFrom")
                if valid_from_ms:
                    valid_from_iso = datetime.fromtimestamp(valid_from_ms / 1000.0, timezone.utc).isoformat()
                else:
                    valid_from_iso = datetime.now(timezone.utc).isoformat()

                # Extract link if present
                links = w.get("links", [])
                direct_url = links[0].get("url") if links else "https://www.natural-hazards.ch"

                warning_item = HazardWarning(
                    warning_id=f"warning-{clean_plz}-{w_type}-{w_level}",
                    warn_type=w_type,
                    warn_type_name=type_name,
                    warn_level=w_level,
                    region_id=reg_id,
                    region_name=f"Region {reg_id} (PLZ {clean_plz})",
                    description=text,
                    valid_from=valid_from_iso,
                    valid_to=None,
                    direct_url=direct_url,
                    source="natural-hazards.ch",
                )
                warnings_list.append(warning_item.to_dict())

            self.last_fetch_success = True

        except (requests.exceptions.RequestException, ValueError) as e:
            self.last_fetch_success = False
            self.last_fetch_error = str(e)
            logger.error(f"Failed to retrieve hazard warnings for PLZ {clean_plz}: {e}")

        return warnings_list

    @log_function_call
    def get_warning_summary(self, plz: str = Config.DEFAULT_ZURICH_PLZ) -> dict[str, Any]:
        """
        Generate a high-level summary of active natural hazard warnings for emergency commanders.

        Args:
            plz: Postal code.

        Returns:
            Dictionary with overall hazard level, count of warnings, and list of alerts.
        """
        warnings = self.get_hazard_warnings(plz=plz)

        if not self.last_fetch_success:
            return {
                "plz": plz,
                "status": "DATA_UNAVAILABLE",
                "data_available": False,
                "error": self.last_fetch_error,
                "has_active_warnings": None,
                "max_warning_level": None,
                "max_warning_label": "Data Unavailable",
                "warning_count": 0,
                "warnings": [],
                "portal_url": "https://www.natural-hazards.ch",
            }

        max_level = max([w["warn_level"] for w in warnings], default=1)
        risk_label = WARN_LEVEL_DESCRIPTIONS.get(max_level, "Unknown")

        return {
            "plz": plz,
            "status": "NOMINAL",
            "data_available": True,
            "has_active_warnings": len(warnings) > 0 and max_level > 1,
            "max_warning_level": max_level,
            "max_warning_label": risk_label,
            "warning_count": len(warnings),
            "warnings": warnings,
            "portal_url": "https://www.natural-hazards.ch",
        }


# Default client instance
_default_warnings_client = HazardWarningsClient()


@log_function_call
def get_hazard_warnings(plz: str = Config.DEFAULT_ZURICH_PLZ) -> list[dict[str, Any]]:
    """
    Public entry point to retrieve active natural hazard warnings for a postal code.

    Args:
        plz: Postal code (default: '800100' for Zurich Center).

    Returns:
        List of normalized hazard warnings.
    """
    return _default_warnings_client.get_hazard_warnings(plz=plz)


@log_function_call
def get_warning_summary(plz: str = Config.DEFAULT_ZURICH_PLZ) -> dict[str, Any]:
    """
    Public entry point to generate a natural hazards summary for emergency decision-making.

    Args:
        plz: Postal code.

    Returns:
        Summary dictionary with max severity level and warning details.
    """
    return _default_warnings_client.get_warning_summary(plz=plz)
