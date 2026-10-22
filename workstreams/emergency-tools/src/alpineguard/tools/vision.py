"""
Gemini vision analysis of drone and camera frames.

Architecture
------------
``GeminiVisionAnalyzer`` sends one image and one question to a Gemini model and returns
the answer text. The ``google-genai`` package is imported only when the analyzer is
used, so the rest of AlpineGuard works without it. Every call is logged with model,
question and answer; the image bytes are never logged.

Use cases
---------
1. ``analyze_image`` asks "Where is the fire front and are people visible?" about a drone frame.
2. Webcam frames from the teammate data layer can use the same analyzer later.
"""

import mimetypes
import os
from pathlib import Path
from typing import Any, Optional

from alpineguard.audit import AuditLog, log_genai_call
from alpineguard.config import Config

VISION_SYSTEM_INSTRUCTION = (
    "You analyse drone and camera images for an emergency operator. Describe only what is "
    "visible in the image. Give positions relative to visible landmarks. If something is not "
    "visible or unclear, say so. Do not guess numbers or causes."
)


class GeminiVisionAnalyzer:
    """Answers questions about images with a Gemini model."""

    def __init__(self, model: str = Config.VISION_MODEL, client: Any = None, audit: Optional[AuditLog] = None) -> None:
        """
        Create the analyzer.

        Parameters:
            model: Gemini model id.
            client: Existing ``google.genai.Client``; created from the API key when None.
            audit: Audit trail for Gemini call records.
        """
        self.model = model
        self._client = client
        self._audit = audit

    def _get_client(self) -> Any:
        if self._client is None:
            from google import genai  # imported here so the package works without google-genai

            api_key = os.environ.get(Config.GEMINI_API_KEY_ENV)
            if not api_key:
                raise RuntimeError(f"Environment variable {Config.GEMINI_API_KEY_ENV} is not set")
            self._client = genai.Client(api_key=api_key)
        return self._client

    def analyze(self, image_path: Path, question: str) -> str:
        """
        Ask a question about an image.

        Parameters:
            image_path: Image file (JPEG or PNG).
            question: What the operator wants to know.

        Returns:
            The model's answer text.

        Raises:
            RuntimeError: If no API key is set.
            OSError: If the image cannot be read.
        """
        from google.genai import types

        data = image_path.read_bytes()
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        response = self._get_client().models.generate_content(
            model=self.model,
            contents=[types.Part.from_bytes(data=data, mime_type=mime_type), question],
            config=types.GenerateContentConfig(system_instruction=VISION_SYSTEM_INSTRUCTION),
        )
        answer = response.text or ""
        log_genai_call(
            self._audit,
            actor="vision_analyzer",
            model=self.model,
            prompt={"question": question, "image": f"{image_path.name} ({len(data)} bytes, not logged)"},
            config={"system_instruction": VISION_SYSTEM_INSTRUCTION},
            output=answer,
        )
        return answer
