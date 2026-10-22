"""
BAFU / FOEN Swiss Hydrological Data Integration Client for CrisisOS.

This module communicates with the Swiss Federal Office for the Environment (BAFU / FOEN)
public GraphQL API (https://data.bafu.admin.ch/api) to retrieve real-time river levels,
discharge volumes, and hydrological monitoring station metadata across Switzerland,
with special focus on the Sihl and Limmat river catchments in Zurich.

Use Cases:
1. Discovering active river monitoring stations filtered by geographical bounding box or river name.
2. Fetching live 10-minute water level (W, m a.s.l.) and discharge (Q, m3/s) observations.
3. Detecting abnormal water discharge or potential flood conditions along the Sihl and Limmat.
4. Normalizing raw BAFU measurements into standard CrisisOS observation schemas.
5. Securing GraphQL queries against parameter injection using strongly-typed variable bindings.
"""

from typing import Any, Optional
import requests

from crisis_data.config import Config
from crisis_data.logger import log_function_call, logger
from crisis_data.models import NormalizedObservation


class BafuHydroClient:
    """Client for querying the BAFU / FOEN GraphQL hydrology endpoint."""

    def __init__(self, endpoint_url: Optional[str] = None, timeout: Optional[int] = None) -> None:
        """
        Initialize the BafuHydroClient.

        Parameters:
            endpoint_url: Optional override for the BAFU GraphQL URL.
            timeout: Optional HTTP request timeout in seconds.
        """
        self.endpoint_url = endpoint_url or Config.BAFU_GRAPHQL_URL
        self.timeout = timeout or Config.BAFU_TIMEOUT_SECONDS

    @log_function_call
    def execute_graphql(self, query: str, variables: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """
        Execute an arbitrary GraphQL query against the BAFU endpoint with error handling.

        Parameters:
            query: The GraphQL query string.
            variables: Optional dictionary of query variables.

        Returns:
            JSON response payload as a dictionary, or fallback dict with 'errors' key on failure.

        Raises:
            Does not raise; returns errors in dictionary payload to prevent crashing callers.
        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = requests.post(
                self.endpoint_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                logger.warning(f"BAFU GraphQL returned errors: {data['errors']}")
            return data
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning(f"BAFU GraphQL request failed: {e}")
            return {"errors": [str(e)], "data": {}}

    @log_function_call
    def get_river_stations(
        self,
        bbox: Optional[dict[str, float]] = None,
        river_name: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Retrieve active hydrological stations optionally filtered by bounding box or river name.

        Parameters:
            bbox: Optional bounding box dict with keys 'min_lat', 'min_lon', 'max_lat', 'max_lon'.
                  If omitted, defaults to the Zurich metropolitan bounding box.
            river_name: Optional river name substring filter (e.g. 'Limmat', 'Sihl').

        Returns:
            List of station dictionaries with station number, name, river, coordinates, and status.
        """
        query = """
        query GetHydrologicalStations {
          water {
            observations {
              stations(where: { status: { _eq: "Aufgebaut" } }) {
                no
                name
                siteName
                riverName
                catchmentName
                latitude
                longitude
                elevation
                status
              }
            }
          }
        }
        """
        result = self.execute_graphql(query)
        stations = result.get("data", {}).get("water", {}).get("observations", {}).get("stations", [])

        effective_bbox = bbox or Config.ZURICH_BBOX
        min_lat = effective_bbox.get("min_lat", -90.0)
        max_lat = effective_bbox.get("max_lat", 90.0)
        min_lon = effective_bbox.get("min_lon", -180.0)
        max_lon = effective_bbox.get("max_lon", 180.0)

        filtered: list[dict[str, Any]] = []
        for s in stations:
            lat = s.get("latitude")
            lon = s.get("longitude")
            r_name = s.get("riverName") or ""
            name = s.get("name") or ""

            # Check river filter
            if river_name and (river_name.lower() not in r_name.lower() and river_name.lower() not in name.lower()):
                continue

            # Check bbox filter
            if lat is not None and lon is not None:
                if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
                    filtered.append(s)
            elif not bbox:
                # Include priority Zurich stations even if coordinates missing
                if s.get("no") in Config.BAFU_PRIMARY_ZURICH_STATIONS:
                    filtered.append(s)

        return filtered

    @log_function_call
    def get_river_measurements(self, station_id: str) -> dict[str, Any]:
        """
        Retrieve the latest live measurements for a specific BAFU station.

        Parameters:
            station_id: BAFU station number (e.g., '2176' for Sihl Sihlhölzli, '2099' for Limmat Unterhard).

        Returns:
            Dictionary containing latest parameter readings (water level W, discharge Q, temperature WT)
            and normalized CrisisOS observations.
        """
        query = """
        query GetLiveStationData($stationNo: String!) {
          water {
            observations {
              data_live(where: { stationNo: { _eq: $stationNo } }) {
                stationNo
                parameterName
                timestamp
                value
                releaseStatus
              }
            }
          }
        }
        """
        result = self.execute_graphql(query, variables={"stationNo": str(station_id).strip()})
        data_live = result.get("data", {}).get("water", {}).get("observations", {}).get("data_live", [])

        # Parameter units mapping based on BAFU hydrology standards
        parameter_units = {
            "W": "m a.s.l.",  # Water level above sea level
            "Q": "m³/s",      # Discharge / flow rate
            "WT": "°C",       # Water temperature
        }
        parameter_descriptions = {
            "W": "water_level",
            "Q": "river_discharge",
            "WT": "water_temperature",
        }

        # Keep the latest entry per parameter
        latest_by_param: dict[str, dict[str, Any]] = {}
        for entry in data_live:
            param = entry.get("parameterName")
            timestamp = entry.get("timestamp")
            if not param or not timestamp:
                continue
            if param not in latest_by_param or timestamp > latest_by_param[param]["timestamp"]:
                latest_by_param[param] = entry

        normalized_obs: list[dict[str, Any]] = []
        for param, entry in latest_by_param.items():
            obs_type = parameter_descriptions.get(param, f"hydrology_{param.lower()}")
            unit = parameter_units.get(param, "dimensionless")
            obs = NormalizedObservation(
                source="BAFU",
                type=obs_type,
                station_id=station_id,
                location=None,  # Station metadata can enrich this
                measurement={"value": entry.get("value"), "unit": unit, "raw_parameter": param},
                observed_at=entry.get("timestamp", ""),
                quality="nominal" if entry.get("releaseStatus") == 0 else "unverified",
                metadata={"release_status": entry.get("releaseStatus")},
            )
            normalized_obs.append(obs.to_dict())

        if "errors" in result and not data_live:
            error_msg = result["errors"][0] if result["errors"] else "Unknown BAFU error"
            return {
                "source": "BAFU",
                "station_id": station_id,
                "status": "DATA_UNAVAILABLE",
                "data_available": False,
                "error": str(error_msg),
                "measurements_count": 0,
                "latest_parameters": {},
                "normalized_observations": [],
            }

        return {
            "source": "BAFU",
            "station_id": station_id,
            "status": "NOMINAL",
            "data_available": True,
            "measurements_count": len(data_live),
            "latest_parameters": latest_by_param,
            "normalized_observations": normalized_obs,
        }


# Module singleton instance
_default_bafu_client = BafuHydroClient()


@log_function_call
def get_river_stations(bbox: Optional[dict[str, float]] = None) -> list[dict[str, Any]]:
    """
    Convenience function to get active hydrological stations in Zurich or a bounding box.

    Parameters:
        bbox: Optional bounding box dictionary.

    Returns:
        List of matching station dictionaries.
    """
    return _default_bafu_client.get_river_stations(bbox=bbox)


@log_function_call
def get_river_measurements(station_id: str) -> dict[str, Any]:
    """
    Convenience function to get live river measurements for a station.

    Parameters:
        station_id: BAFU station identifier (e.g. '2176' or '2099').

    Returns:
        Structured live measurements and normalized observations.
    """
    return _default_bafu_client.get_river_measurements(station_id=station_id)
