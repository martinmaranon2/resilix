"""
Swiss Population and Building Exposure (BFS) Integration for CrisisOS Switzerland.

This module accesses official Swiss Federal Statistical Office (Bundesamt für Statistik, BFS)
data sources, primarily the Federal Register of Buildings and Dwellings (Eidg. Gebäude- und
Wohnungsregister, GWR: `ch.bfs.gebaeude_wohnungs_register`) and municipal population statistics (STATPOP).

During flood or earthquake crises in Zurich, emergency coordinators must determine not only where
hazards exist, but what human populations and physical structures are exposed. This module enables
CrisisOS to identify building inventories (construction epoch, number of storeys, surface footprint)
and municipal population density within flood-vulnerable postal sectors.

Use Cases:
1. Querying official building registers in Zurich postal zones (e.g. 8001 Altstadt, 8005 Industriequartier).
2. Assessing vulnerability profiles based on building construction years, residential floors, and surface areas.
3. Calculating exposed population density metrics for emergency evacuations.
4. Supplying building inventory exposure data to the Gemini multimodal agent.
5. Providing resilient type-safe attribute parsing and simulated fallback payloads during network or register outages.
"""

from typing import Any, Optional
import requests

from crisis_data.config import Config
from crisis_data.logger import log_function_call, logger
from crisis_data.models import BuildingExposureInfo
from crisis_data.swisstopo import lv95_to_wgs84


class BfsPopulationClient:
    """Client for querying BFS building registers and population density metrics."""

    def __init__(self, timeout_seconds: Optional[int] = None) -> None:
        """
        Initialize the BFS population and building client.

        Args:
            timeout_seconds: Network request timeout in seconds.
        """
        self.timeout: int = timeout_seconds or Config.BFS_TIMEOUT_SECONDS
        self.search_url: str = Config.BFS_GWR_SEARCH_URL
        self.gwr_layer: str = Config.BFS_GWR_LAYER
        self.last_fetch_success: bool = True
        self.last_fetch_error: Optional[str] = None

    @log_function_call
    def get_building_exposure(
        self,
        postal_code: int = 8001,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """
        Retrieve official building records from the BFS GWR for a given postal code.

        Args:
            postal_code: 4-digit Swiss postal code (e.g. 8001, 8005, 8002).
            limit: Maximum number of building records to return.

        Returns:
            List of normalized building exposure dictionaries.
        """
        params = {
            "layer": self.gwr_layer,
            "searchText": str(postal_code),
            "searchField": "dplz4",
            "returnGeometry": "false",
        }

        buildings: list[dict[str, Any]] = []
        try:
            response = requests.get(
                self.search_url,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])

            for res in results[:limit]:
                attrs = res.get("attributes", {})
                egid = str(attrs.get("egid") or "")
                street = attrs.get("strname_deinr") or attrs.get("label") or "Unknown Street"
                house_no = attrs.get("deinr") or ""

                # Defensively parse postal code
                plz = postal_code
                try:
                    if attrs.get("dplz4") is not None:
                        plz = int(attrs.get("dplz4"))
                except (ValueError, TypeError):
                    plz = postal_code

                commune = attrs.get("ggdename") or "Zürich"

                # Defensively parse construction year
                year_built: Optional[int] = None
                raw_year = attrs.get("gbauj")
                if raw_year is not None:
                    try:
                        year_built = int(raw_year)
                    except (ValueError, TypeError):
                        year_built = None

                # Defensively parse floor count
                floors: Optional[int] = None
                raw_floors = attrs.get("gastw")
                if raw_floors is not None:
                    try:
                        floors = int(raw_floors)
                    except (ValueError, TypeError):
                        floors = None

                # Defensively parse ground surface area
                area_m2: Optional[float] = None
                raw_area = attrs.get("garea")
                if raw_area is not None:
                    try:
                        area_m2 = float(raw_area)
                    except (ValueError, TypeError):
                        area_m2 = None

                # Coordinates in LV95 (gkode, gkodn)
                east = attrs.get("gkode")
                north = attrs.get("gkodn")
                lat, lon = None, None
                if east and north:
                    try:
                        lat, lon = lv95_to_wgs84(float(east), float(north))
                        lat = round(lat, 5)
                        lon = round(lon, 5)
                    except (ValueError, TypeError, Exception) as ce:
                        logger.debug(f"Coordinate conversion error for EGID {egid}: {ce}")

                building = BuildingExposureInfo(
                    egid=egid,
                    street=street,
                    house_number=str(house_no),
                    postal_code=plz,
                    municipality=commune,
                    year_built=year_built,
                    floors=floors,
                    area_m2=area_m2,
                    latitude=lat,
                    longitude=lon,
                    population_density_km2=Config.BFS_ZURICH_DENSITY_PER_KM2,
                    source="BFS_GWR",
                    is_simulated=False,
                )
                buildings.append(building.to_dict())

            self.last_fetch_success = True
            self.last_fetch_error = None

        except (requests.exceptions.RequestException, ValueError, KeyError) as e:
            self.last_fetch_success = False
            self.last_fetch_error = str(e)
            logger.error(f"Failed to query BFS building register for PLZ {postal_code}: {e}")
            fallback_building = BuildingExposureInfo(
                egid="bfs-error-fallback",
                street="Service Unavailable Fallback",
                house_number="N/A",
                postal_code=postal_code,
                municipality="Zürich",
                year_built=None,
                floors=None,
                area_m2=None,
                latitude=Config.ZURICH_LAT,
                longitude=Config.ZURICH_LON,
                population_density_km2=Config.BFS_ZURICH_DENSITY_PER_KM2,
                source="BFS_GWR",
                is_simulated=True,
            )
            return [fallback_building.to_dict()]

        return buildings

    @log_function_call
    def get_population_exposure_metrics(self, postal_code: int = 8001) -> dict[str, Any]:
        """
        Compute an aggregated exposure and demographic profile for a Zurich postal sector.

        Args:
            postal_code: 4-digit Swiss postal code.

        Returns:
            Dictionary containing population estimates, building statistics, and vulnerability summary.
        """
        buildings = self.get_building_exposure(postal_code=postal_code, limit=50)

        if not self.last_fetch_success:
            return {
                "status": "DATA_UNAVAILABLE",
                "postal_code": postal_code,
                "municipality": "Zürich",
                "canton": "ZH",
                "total_municipality_population": Config.BFS_ZURICH_POPULATION_ESTIMATE,
                "municipality_area_km2": Config.BFS_ZURICH_AREA_KM2,
                "population_density_per_km2": Config.BFS_ZURICH_DENSITY_PER_KM2,
                "sample_buildings_analyzed": 0,
                "average_building_floors": 0.0,
                "historic_buildings_pre_1950": 0,
                "statpop_map_url": "https://map.geo.admin.ch/?layers=ch.bfs.volkszaehlung-bevoelkerungsstatistik_einwohner",
                "sample_buildings": buildings[:5],
                "source": "BFS_STATPOP_GWR",
                "is_simulated": True,
                "error": self.last_fetch_error,
            }

        # Calculate metrics
        buildings_count = len(buildings)
        avg_floors = 0.0
        floors_list = [b["floors"] for b in buildings if b.get("floors") is not None]
        if floors_list:
            avg_floors = round(sum(floors_list) / len(floors_list), 1)

        historic_buildings = len([b for b in buildings if b.get("year_built") and b["year_built"] < 1950])

        return {
            "status": "OPERATIONAL",
            "postal_code": postal_code,
            "municipality": "Zürich",
            "canton": "ZH",
            "total_municipality_population": Config.BFS_ZURICH_POPULATION_ESTIMATE,
            "municipality_area_km2": Config.BFS_ZURICH_AREA_KM2,
            "population_density_per_km2": Config.BFS_ZURICH_DENSITY_PER_KM2,
            "sample_buildings_analyzed": buildings_count,
            "average_building_floors": avg_floors,
            "historic_buildings_pre_1950": historic_buildings,
            "statpop_map_url": "https://map.geo.admin.ch/?layers=ch.bfs.volkszaehlung-bevoelkerungsstatistik_einwohner",
            "sample_buildings": buildings[:5],
            "source": "BFS_STATPOP_GWR",
            "is_simulated": False,
        }


# Default client instance
_default_bfs_client = BfsPopulationClient()


@log_function_call
def get_building_exposure(
    postal_code: int = 8001,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """
    Public entry point to retrieve building register records for an area.

    Args:
        postal_code: 4-digit postal code (default: 8001).
        limit: Maximum number of building records.

    Returns:
        List of normalized building records.
    """
    return _default_bfs_client.get_building_exposure(
        postal_code=postal_code,
        limit=limit,
    )


@log_function_call
def get_population_exposure_metrics(postal_code: int = 8001) -> dict[str, Any]:
    """
    Public entry point to generate demographic and building exposure metrics.

    Args:
        postal_code: 4-digit postal code.

    Returns:
        Demographic and infrastructure exposure summary dictionary.
    """
    return _default_bfs_client.get_population_exposure_metrics(postal_code=postal_code)
