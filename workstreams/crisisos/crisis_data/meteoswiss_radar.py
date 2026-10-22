"""
MeteoSwiss Precipitation Radar STAC Integration Client for CrisisOS Switzerland.

This module interfaces with the MeteoSwiss Open Government Data Precipitation Radar
collection on the Swiss Federal Geodata STAC catalog
(https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-radar-precip).
It queries the radar catalog, identifies active composite items across Switzerland,
and exposes radar metadata, spatial bounding polygons, scan timestamps, and download URIs.

Use Cases:
1. Checking availability and freshness of high-resolution composite radar scans.
2. Providing radar asset URLs (5-minute HDF5 scans) for secondary processing or geospatial visualization.
3. Exposing radar coverage bounds and timestamps to the Gemini reasoning agent.
4. Documenting HDF5 data formats and operational constraints during hackathon triage.
"""

from typing import Any, Optional
import requests

from crisis_data.config import Config
from crisis_data.logger import log_function_call, logger
from crisis_data.models import current_utc_iso


class MeteoSwissRadarClient:
    """Client for querying the MeteoSwiss precipitation radar STAC collection."""

    def __init__(self, stac_url: Optional[str] = None, timeout: Optional[int] = None) -> None:
        """
        Initialize the MeteoSwissRadarClient.

        Parameters:
            stac_url: Optional override for the radar STAC collection URL.
            timeout: Optional HTTP request timeout in seconds.
        """
        self.stac_url = stac_url or Config.METEOSWISS_RADAR_STAC_URL
        self.timeout = timeout or Config.METEOSWISS_RADAR_TIMEOUT_SECONDS

    @log_function_call
    def get_precipitation_radar(self, limit: int = 2) -> dict[str, Any]:
        """
        Retrieve recent precipitation radar items and asset metadata from the STAC catalog.

        Parameters:
            limit: Maximum number of recent radar catalog items to inspect (default 2).

        Returns:
            Dictionary with collection metadata, spatial bounding polygon, latest scan items,
            and HDF5 asset download references.
        """
        items_url = f"{self.stac_url}/items?limit={limit}"
        try:
            response = requests.get(items_url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"Failed to fetch MeteoSwiss radar STAC items: {e}")
            return {
                "source": "MeteoSwiss Radar",
                "status": "DATA_UNAVAILABLE",
                "is_simulated": True,
                "error": str(e),
                "collection_id": "ch.meteoschweiz.ogd-radar-precip",
                "spatial_coverage": "Switzerland (Alps & Plateau)",
                "bounding_box_wgs84": [5.96, 45.82, 10.49, 47.81],
                "latest_item_id": None,
                "latest_update": None,
                "format": "HDF5 (.h5)",
                "retrieved_at": current_utc_iso(),
                "items": [],
            }

        features = data.get("features", [])
        if not features:
            return {
                "source": "MeteoSwiss Radar",
                "status": "NO_ITEMS_FOUND",
                "message": "No active radar features returned from STAC collection.",
            }

        parsed_items: list[dict[str, Any]] = []
        for feat in features:
            feat_id = feat.get("id")
            props = feat.get("properties", {})
            bbox = feat.get("bbox")
            geometry = feat.get("geometry")
            assets = feat.get("assets", {})

            # Filter or sample recent HDF5 radar scan assets
            # HDF5 assets follow naming: tzc[YY][DOY][HHMM]vl.[version].h5
            asset_keys = list(assets.keys())
            sample_asset_refs = []
            for k in asset_keys[-5:]:  # Take the last 5 scans in this feature
                asset_obj = assets[k]
                sample_asset_refs.append({
                    "name": k,
                    "href": asset_obj.get("href"),
                    "type": asset_obj.get("type", "application/x-hdf5"),
                })

            parsed_items.append({
                "item_id": feat_id,
                "title": props.get("title"),
                "datetime": props.get("datetime"),
                "created": props.get("created"),
                "updated": props.get("updated"),
                "bbox": bbox,
                "geometry_type": geometry.get("type") if geometry else None,
                "total_scans_in_item": len(asset_keys),
                "latest_sample_scans": sample_asset_refs,
            })

        latest_item = parsed_items[0] if parsed_items else {}

        return {
            "source": "MeteoSwiss Radar",
            "collection_id": "ch.meteoschweiz.ogd-radar-precip",
            "spatial_coverage": "Switzerland (Alps & Plateau)",
            "bounding_box_wgs84": latest_item.get("bbox"),
            "latest_item_id": latest_item.get("item_id"),
            "latest_update": latest_item.get("updated"),
            "format": "HDF5 (.h5)",
            "processing_status": "ASSET_METADATA_EXPOSED",
            "note": "Raw 5-minute radar composites are delivered as HDF5 arrays. In CrisisOS, "
                    "Open-Meteo and SwissMetNet ground stations supply instant millimeter precipitation values, "
                    "while radar STAC provides spatial verification and raw scan links.",
            "retrieved_at": current_utc_iso(),
            "items": parsed_items,
        }


# Module singleton instance
_default_radar_client = MeteoSwissRadarClient()


@log_function_call
def get_precipitation_radar() -> dict[str, Any]:
    """
    Convenience wrapper to retrieve recent radar metadata and scan asset links.

    Returns:
        Structured radar catalog metadata and asset links.
    """
    return _default_radar_client.get_precipitation_radar()
