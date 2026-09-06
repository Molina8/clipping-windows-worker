"""Wrapper de FFprobe para inspeccionar archivos de vídeo/audio."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import Settings
from app.utils.logging import get_logger
from app.utils.subprocess import run_command

logger = get_logger("ffprobe")


class FFprobeTool:
    """Encapsula la detección y uso de ffprobe."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._binary = settings.ffprobe_path or "ffprobe"

    @property
    def available(self) -> bool:
        try:
            run_command([self._binary, "-version"], timeout=10)
            return True
        except Exception:  # noqa: BLE001 - cualquier error = no disponible
            return False

    def probe(self, path: str | Path) -> dict[str, Any]:
        """Devuelve el JSON completo de ffprobe para un archivo."""
        result = run_command(
            [
                self._binary,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            timeout=60,
        )
        return json.loads(result.stdout)

    def get_video_stream(self, path: str | Path) -> dict[str, Any] | None:
        """Devuelve el primer stream de vídeo, o None si no hay."""
        data = self.probe(path)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                return stream
        return None

    def get_audio_stream(self, path: str | Path) -> dict[str, Any] | None:
        """Devuelve el primer stream de audio, o None si no hay."""
        data = self.probe(path)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "audio":
                return stream
        return None

    def get_duration(self, path: str | Path) -> float | None:
        """Devuelve la duración en segundos, o None si no se puede determinar."""
        data = self.probe(path)
        duration = data.get("format", {}).get("duration")
        if duration is not None:
            try:
                return float(duration)
            except (TypeError, ValueError):
                return None
        return None

    def get_resolution(self, path: str | Path) -> tuple[int, int] | None:
        """Devuelve (width, height) del stream de vídeo, o None."""
        stream = self.get_video_stream(path)
        if not stream:
            return None
        width = stream.get("width")
        height = stream.get("height")
        if width is None or height is None:
            return None
        return int(width), int(height)

    def get_fps(self, path: str | Path) -> float | None:
        """Devuelve los FPS del stream de vídeo, o None."""
        stream = self.get_video_stream(path)
        if not stream:
            return None
        avg = stream.get("avg_frame_rate")
        if not avg or "/" not in avg:
            return None
        try:
            num, den = avg.split("/")
            den = float(den)
            if den == 0:
                return None
            return float(num) / den
        except (ValueError, ZeroDivisionError):
            return None
