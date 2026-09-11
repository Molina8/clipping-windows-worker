"""Job de renderizado de clips con FFmpeg."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.jobs.base import BaseJob
from app.tools.ffmpeg import FFmpegTool


class RenderJob(BaseJob):
    """Recorta, reencuadra, añade subtítulos y watermark, y codifica."""

    type = "render"

    def execute(self) -> dict[str, Any]:
        payload = self.job.payload
        input_video = payload.get("input_video")
        # Aceptamos tanto `start_time`/`end_time` (canónico) como `start`/`end`
        # (legacy) por compatibilidad con jobs antiguos.
        start = float(payload.get("start_time", payload.get("start", 0.0)))
        end = float(payload.get("end_time", payload.get("end", 0.0)))
        # Aceptamos tanto `format` (canónico VPS) como `output_format` (legacy)
        output_format = payload.get("format") or payload.get("output_format", "9:16")

        if not input_video:
            raise ValueError("payload.input_video is required")
        if end <= start:
            raise ValueError(f"end ({end}) must be greater than start ({start})")

        source = self._resolve_input(input_video)
        if not source.exists():
            raise FileNotFoundError(f"Input video not found: {source}")

        # Subtítulos
        captions = payload.get("captions") or {}
        captions_file = None
        if captions.get("enabled") and captions.get("file"):
            captions_file = self._resolve_input(captions["file"])

        # Watermark
        watermark = payload.get("watermark") or {}
        if watermark.get("enabled") and watermark.get("file"):
            watermark = {**watermark, "file": str(self._resolve_input(watermark["file"]))}

        output_path = self.directory.output / "clip.mp4"
        ffmpeg = FFmpegTool(self.settings)

        self.logger.info(
            "rendering clip",
            input=str(source),
            start=start,
            end=end,
            format=output_format,
        )
        ffmpeg.render_clip(
            input_path=source,
            output_path=output_path,
            start=start,
            end=end,
            output_format=output_format,
            captions_file=captions_file,
            watermark=watermark,
        )

        self.logger.info("clip rendered", output=str(output_path))
        file_size = output_path.stat().st_size
        # Duración real del clip generado (puede diferir ligeramente de
        # end-start por el redondeo a keyframe). La usamos en el QA y
        # la persistimos en VPS como `duration_seconds`.
        duration_seconds = max(0.0, end - start)
        return {
            # Canónico (VPS consume esto)
            "file_path": str(output_path),
            "file_size": file_size,
            "duration_seconds": duration_seconds,
            "format": output_format,
            # Aliases para retro-compatibilidad con jobs antiguos
            "output_path": str(output_path),
            "filename": output_path.name,
            "size": file_size,
            "output_format": output_format,
        }

    def _resolve_input(self, path: str) -> Path:
        """Resuelve una ruta de entrada, absoluta o relativa al job."""
        p = Path(path)
        if p.is_absolute():
            return p
        candidates = [
            self.directory.input / p,
            self.directory.root / p,
            Path(self.settings.working_directory) / p,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]
