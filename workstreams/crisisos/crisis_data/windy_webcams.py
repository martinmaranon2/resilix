"""
Windy Webcams API V3 Integration Client for CrisisOS Switzerland.

This module connects to the Windy Webcams V3 API (https://api.windy.com/webcams/docs)
to locate public cameras around Zurich rivers, bridges, and flood-prone areas,
and to retrieve fresh webcam imagery for multimodal visual analysis by Gemini.

Use Cases:
1. Searching for active webcams within a radial distance of a specific coordinate (e.g. Zurich Limmat/Sihl).
2. Fetching current high-resolution image URLs and verifying their availability.
3. Downloading webcam image bytes for direct input to Gemini 2.5 Flash / Pro visual reasoning.
4. Monitoring camera status, capture freshness, and gracefully handling missing or expired credentials.
"""

from datetime import datetime, timezone
from typing import Any, Optional
import requests

from crisis_data.config import Config
from crisis_data.logger import log_function_call, logger
from crisis_data.models import CameraMetadata


class WindyWebcamsClient:
    """Client for querying the Windy Webcams V3 API."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: Optional[int] = None) -> None:
        """
        Initialize the WindyWebcamsClient.

        Parameters:
            api_key: Optional Windy API key. If omitted, uses Config.WINDY_API_KEY.
            base_url: Optional override for the Windy Webcams V3 API endpoint.
            timeout: Optional HTTP request timeout in seconds.
        """
        self.api_key = api_key or Config.WINDY_API_KEY
        self.base_url = base_url or Config.WINDY_WEBCAMS_BASE_URL
        self.timeout = timeout or Config.WINDY_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        """
        Check if an API key is configured.

        Returns:
            True if an API key is present, False otherwise.
        """
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    @log_function_call
    def get_nearby_webcams(
        self,
        latitude: float = Config.ZURICH_LAT,
        longitude: float = Config.ZURICH_LON,
        radius_km: float = Config.DEFAULT_RADIUS_KM,
        limit: int = 10
    ) -> list[dict[str, Any]]:
        """
        Retrieve active webcams near a geographic coordinate.

        Parameters:
            latitude: Center latitude in WGS84 degrees.
            longitude: Center longitude in WGS84 degrees.
            radius_km: Search radius in kilometers (defaults to 15 km).
            limit: Maximum number of cameras to return.

        Returns:
            List of camera metadata dictionaries.

        Raises:
            PermissionError: If no API key is configured.
            requests.RequestException: If the Windy API responds with an HTTP error.
        """
        if not self.is_configured():
            logger.warning(
                "Windy Webcams API key is not configured. Set WINDY_API_KEY environment variable."
            )
            return self._get_fallback_zurich_cameras()

        headers = {
            "x-windy-api-key": self.api_key,  # type: ignore
            "Accept": "application/json",
        }
        # Windy V3 nearby parameter format: latitude,longitude,radius_km
        params = {
            "nearby": f"{latitude},{longitude},{int(radius_km)}",
            "include": "images,location",
            "limit": limit,
        }

        try:
            response = requests.get(self.base_url, headers=headers, params=params, timeout=self.timeout)
            if response.status_code in (401, 403):
                logger.warning(f"Windy API authentication failed (HTTP {response.status_code}). Using fallback cameras.")
                return self._get_fallback_zurich_cameras()
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"Windy API request failed: {e}. Using fallback cameras.")
            return self._get_fallback_zurich_cameras()

        webcams = data.get("webcams", [])

        results: list[dict[str, Any]] = []
        for cam in webcams:
            cam_id = str(cam.get("webcamId", ""))
            title = cam.get("title", f"Webcam {cam_id}")
            loc = cam.get("location", {})
            images = cam.get("images", {})
            current_image = images.get("current", {})
            daylight_image = images.get("daylight", {})

            # Select best available image URL
            image_url = current_image.get("preview") or current_image.get("icon") or daylight_image.get("preview")
            preview_url = current_image.get("thumbnail") or daylight_image.get("thumbnail")
            status = cam.get("status", "unknown")

            meta = CameraMetadata(
                camera_id=cam_id,
                title=title,
                location={"latitude": loc.get("latitude"), "longitude": loc.get("longitude")},
                image_url=image_url,
                preview_url=preview_url,
                updated_at=cam.get("lastUpdatedOn"),
                status=status,
                source="Windy V3",
                is_simulated=False,
            )
            results.append(meta.to_dict())

        return results

    @log_function_call
    def get_webcam_image(self, camera_id: str) -> dict[str, Any]:
        """
        Retrieve live image bytes and metadata for a specific camera ID.

        Parameters:
            camera_id: Unique identifier for the webcam.

        Returns:
            Dictionary containing image metadata, mime_type, and raw image bytes.
        """
        # First retrieve camera metadata
        if not self.is_configured():
            logger.warning("Windy API key not configured; using fallback image inspection.")
            return {
                "camera_id": camera_id,
                "status": "NEEDS_API_KEY",
                "message": "Set WINDY_API_KEY in .env to fetch live Windy webcam images.",
                "image_bytes": None,
            }

        headers = {"x-windy-api-key": self.api_key, "Accept": "application/json"}  # type: ignore
        url = f"{self.base_url}/{camera_id}?include=images,location"
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            cam = response.json()

            images = cam.get("images", {})
            image_url = images.get("current", {}).get("preview") or images.get("daylight", {}).get("preview")

            if not image_url:
                return {
                    "camera_id": camera_id,
                    "status": "NO_IMAGE_URL",
                    "message": f"No valid image URL found for camera {camera_id}",
                    "image_bytes": None,
                }

            # Fetch image bytes
            img_res = requests.get(image_url, timeout=self.timeout)
            img_res.raise_for_status()

            return {
                "camera_id": camera_id,
                "status": "NOMINAL",
                "title": cam.get("title"),
                "image_url": image_url,
                "content_type": img_res.headers.get("Content-Type", "image/jpeg"),
                "image_bytes": img_res.content,
                "byte_count": len(img_res.content),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"Failed to fetch image for webcam {camera_id}: {e}")
            return {
                "camera_id": camera_id,
                "status": "ERROR",
                "message": str(e),
                "image_bytes": None,
            }

    def _get_fallback_zurich_cameras(self) -> list[dict[str, Any]]:
        """
        Provide public camera references in Zurich for offline or key-pending development.

        Returns:
            List of reference camera metadata objects.
        """
        fallback_cams = [
            CameraMetadata(
                camera_id="zurich_quaibruecke_ref",
                title="Zürich Quaibrücke (Limmat Outlet)",
                location={"latitude": 47.3670, "longitude": 8.5430},
                image_url=None,
                preview_url=None,
                updated_at=None,
                status="pending_credentials",
                source="Windy (Pending Key)",
                is_simulated=True,
            ),
            CameraMetadata(
                camera_id="zurich_sihlhölzli_ref",
                title="Zürich Sihlhölzli (River Sihl)",
                location={"latitude": 47.3677, "longitude": 8.5261},
                image_url=None,
                preview_url=None,
                updated_at=None,
                status="pending_credentials",
                source="Windy (Pending Key)",
                is_simulated=True,
            ),
        ]
        return [c.to_dict() for c in fallback_cams]


# Module singleton instance
_default_windy_client = WindyWebcamsClient()


@log_function_call
def get_nearby_webcams(
    latitude: float = Config.ZURICH_LAT,
    longitude: float = Config.ZURICH_LON,
    radius_km: float = Config.DEFAULT_RADIUS_KM
) -> list[dict[str, Any]]:
    """
    Convenience function to find public webcams near a location.

    Parameters:
        latitude: Target latitude in WGS84 degrees.
        longitude: Target longitude in WGS84 degrees.
        radius_km: Radius in kilometers.

    Returns:
        List of camera metadata records.
    """
    return _default_windy_client.get_nearby_webcams(latitude=latitude, longitude=longitude, radius_km=radius_km)


@log_function_call
def get_webcam_image(camera_id: str) -> dict[str, Any]:
    """
    Convenience function to fetch image bytes and metadata for a camera.

    Parameters:
        camera_id: The camera identifier.

    Returns:
        Dictionary containing image metadata and bytes.
    """
    return _default_windy_client.get_webcam_image(camera_id=camera_id)
