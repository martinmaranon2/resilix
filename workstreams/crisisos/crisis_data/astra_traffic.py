"""
ASTRA Road Traffic Integration for CrisisOS Switzerland.

This module interfaces with the Federal Roads Office (ASTRA / FEDRO) traffic data platform
via opentransportdata.swiss, delivering real-time road traffic situations, disruptions,
closures, and congestion data across the Swiss national road network with a focus on Canton Zurich.

During flood events (such as rising water levels on the Sihl or Limmat), major arterial routes
(e.g., A1, A3W near Sihlquai / Brunau, Hardbrücke) and bridge crossings are at risk of inundation
or emergency closure. Real-time traffic alerts allow CrisisOS to identify blocked evacuation corridors
and reroute emergency logistics.

Use Cases:
1. Identifying active road closures and flood-related disruptions on Zurich expressways (A1, A3, A4).
2. Estimating delays and traffic obstructions affecting emergency service response times.
3. Supplying traffic situation data to the Gemini reasoning agent to plan safe dispatch routes.
4. Providing graceful fallback when the opentransportdata.swiss API key is not configured.
5. Providing degraded fallback incident structures when XML parsing or upstream network feeds fail.
"""

import xml.etree.ElementTree as ET
from typing import Any, Optional
import requests

from crisis_data.config import Config
from crisis_data.logger import log_function_call, logger
from crisis_data.models import TrafficIncident, current_utc_iso


class AstraTrafficClient:
    """Client for retrieving road traffic situations from ASTRA via opentransportdata.swiss."""

    def __init__(self, api_key: Optional[str] = None, timeout_seconds: Optional[int] = None) -> None:
        """
        Initialize the ASTRA traffic client.

        Args:
            api_key: Optional API key for opentransportdata.swiss. Defaults to Config.OTD_API_KEY.
            timeout_seconds: Network request timeout in seconds.
        """
        self.api_key: Optional[str] = api_key or Config.OTD_API_KEY
        self.timeout: int = timeout_seconds or Config.ASTRA_TIMEOUT_SECONDS
        self.endpoint: str = Config.ASTRA_TRAFFIC_URL

    @log_function_call
    def has_api_key(self) -> bool:
        """
        Check whether an opentransportdata.swiss API key is configured.

        Returns:
            True if an API key is available, False otherwise.
        """
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    @log_function_call
    def get_traffic_incidents(self, road_filter: Optional[str] = None) -> list[dict[str, Any]]:
        """
        Retrieve live road traffic incidents, closures, and congestion warnings.

        If no API key is provided, a graceful fallback response is returned indicating
        the authentication requirement while maintaining pipeline stability.

        Args:
            road_filter: Optional road identifier to filter (e.g., 'A1', 'A3', 'A3W').

        Returns:
            List of normalized traffic incident dictionaries.
        """
        if not self.has_api_key():
            logger.warning(
                "No ASTRA / opentransportdata.swiss API key found. "
                "Register at https://opentransportdata.swiss/en/register/ and set OTD_API_KEY in .env."
            )
            return [
                TrafficIncident(
                    incident_id="astra-auth-required",
                    road_number=road_filter or "A3W / Sihlquai",
                    direction="Zurich City",
                    incident_type="auth_required",
                    description="ASTRA live traffic feed requires OTD_API_KEY from opentransportdata.swiss",
                    location={"latitude": Config.ZURICH_LAT, "longitude": Config.ZURICH_LON},
                    is_closed=False,
                    delay_minutes=0,
                    updated_at=current_utc_iso(),
                    source="ASTRA_FEDRO",
                    is_simulated=True,
                ).to_dict()
            ]

        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/xml",
            "User-Agent": Config.OVERPASS_USER_AGENT,
        }

        # Standard DATEX II SOAP / Pull envelope
        soap_body = """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tdp="http://datex2.eu/schema/2/2_0">
   <soapenv:Header/>
   <soapenv:Body>
      <tdp:pullTrafficSituationsRequest/>
   </soapenv:Body>
</soapenv:Envelope>"""

        try:
            response = requests.post(
                self.endpoint,
                data=soap_body,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return self._parse_datex_xml(response.text, road_filter)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching ASTRA traffic situations: {e}")
            return [
                TrafficIncident(
                    incident_id="astra-error",
                    road_number=road_filter or "Unknown",
                    direction=None,
                    incident_type="network_error",
                    description=f"Error connecting to ASTRA traffic platform: {str(e)}",
                    location=None,
                    is_closed=False,
                    delay_minutes=None,
                    updated_at=current_utc_iso(),
                    source="ASTRA_FEDRO",
                    is_simulated=True,
                ).to_dict()
            ]

    def _parse_datex_xml(self, xml_text: str, road_filter: Optional[str] = None) -> list[dict[str, Any]]:
        """
        Parse DATEX II XML payload into normalized traffic incident records.

        Args:
            xml_text: Raw XML response from opentransportdata.swiss.
            road_filter: Optional road identifier filter.

        Returns:
            List of parsed and normalized incident records, or a fallback simulated record on XML parse error.
        """
        incidents: list[dict[str, Any]] = []
        try:
            root = ET.fromstring(xml_text)
            # DATEX II namespaces
            ns = {"d2": "http://datex2.eu/schema/2/2_0"}
            
            for sit in root.findall(".//d2:situationRecord", ns):
                rec_id = sit.attrib.get("id", "unknown-record")
                road_elem = sit.find(".//d2:roadNumber", ns)
                road = road_elem.text if road_elem is not None and road_elem.text else "National Road"

                if road_filter and road_filter.upper() not in road.upper():
                    continue

                comment_elem = sit.find(".//d2:comment//d2:value", ns)
                description = comment_elem.text if comment_elem is not None and comment_elem.text else "Traffic situation"

                # Check closure status
                is_closed = "closed" in description.lower() or "gesperrt" in description.lower()

                # Extract coordinates if present
                lat_elem = sit.find(".//d2:latitude", ns)
                lon_elem = sit.find(".//d2:longitude", ns)
                location = None
                if lat_elem is not None and lon_elem is not None and lat_elem.text and lon_elem.text:
                    try:
                        location = {
                            "latitude": float(lat_elem.text),
                            "longitude": float(lon_elem.text),
                        }
                    except ValueError:
                        pass

                incident = TrafficIncident(
                    incident_id=rec_id,
                    road_number=road,
                    direction=None,
                    incident_type="closure" if is_closed else "traffic_event",
                    description=description,
                    location=location,
                    is_closed=is_closed,
                    delay_minutes=None,
                    updated_at=current_utc_iso(),
                    source="ASTRA_FEDRO",
                    is_simulated=False,
                )
                incidents.append(incident.to_dict())
        except ET.ParseError as pe:
            logger.error(f"Failed to parse ASTRA DATEX II XML: {pe}")
            fallback_incident = TrafficIncident(
                incident_id="astra-xml-parse-error",
                road_number=road_filter or "UNKNOWN",
                direction=None,
                incident_type="xml_parse_error",
                description=f"Failed to parse ASTRA DATEX II XML payload: {pe}",
                location=None,
                is_closed=False,
                delay_minutes=None,
                updated_at=current_utc_iso(),
                source="ASTRA_FEDRO",
                is_simulated=True,
            )
            return [fallback_incident.to_dict()]

        return incidents


# Default client instance
_default_astra_client = AstraTrafficClient()


@log_function_call
def get_traffic_incidents(road_filter: Optional[str] = None) -> list[dict[str, Any]]:
    """
    Public entry point to retrieve active road traffic incidents and road closures.

    Args:
        road_filter: Optional road code to filter (e.g. 'A1', 'A3').

    Returns:
        List of normalized traffic incident dictionaries.
    """
    return _default_astra_client.get_traffic_incidents(road_filter=road_filter)
