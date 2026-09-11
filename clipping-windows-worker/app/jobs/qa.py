"""Job de QA técnico de vídeo con FFprobe."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.jobs.base import BaseJob
from app.tools.ffprobe import FFprobeTool


class QAJob(BaseJob):
    """Valida propiedades técnicas de un vídeo contra unas reglas."""

    type = "qa"

    def execute(self) -> dict[str, Any]:
        payload = self.job.payload
        # Aceptamos `file_path` (canónico VPS) y `video` (legacy)
        video = payload.get("file_path") or payload.get("video")
        rules = payload.get("rules") or {}

        if not video:
            raise ValueError("payload.file_path is required")

        source = self._resolve_input(video)
        if not source.exists():
            raise FileNotFoundError(f"Video not found: {source}")

        ffprobe = FFprobeTool(self.settings)
        checks: list[dict[str, Any]] = []

        # --- Duración ---
        duration = ffprobe.get_duration(source)
        min_dur = rules.get("min_duration")
        max_dur = rules.get("max_duration")
        if min_dur is not None or max_dur is not None:
            ok = True
            if min_dur is not None and (duration is None or duration < min_dur):
                ok = False
            if max_dur is not None and (duration is None or duration > max_dur):
                ok = False
            checks.append(
                {
                    "name": "duration",
                    "status": "PASS" if ok else "FAIL",
                    "actual": duration,
                    "expected": f"{min_dur}-{max_dur}" if min_dur is not None or max_dur is not None else None,
                }
            )

        # --- Resolución ---
        resolution = ffprobe.get_resolution(source)
        width = rules.get("width")
        height = rules.get("height")
        if width is not None or height is not None:
            ok = True
            if resolution is None:
                ok = False
            else:
                if width is not None and resolution[0] != width:
                    ok = False
                if height is not None and resolution[1] != height:
                    ok = False
            checks.append(
                {
                    "name": "resolution",
                    "status": "PASS" if ok else "FAIL",
                    "actual": f"{resolution[0]}x{resolution[1]}" if resolution else None,
                    "expected": f"{width}x{height}" if width is not None or height is not None else None,
                }
            )

        # --- FPS ---
        fps = ffprobe.get_fps(source)
        min_fps = rules.get("min_fps")
        if min_fps is not None:
            ok = fps is not None and fps >= min_fps
            checks.append(
                {
                    "name": "fps",
                    "status": "PASS" if ok else "FAIL",
                    "actual": fps,
                    "expected": f">={min_fps}",
                }
            )

        # --- Audio presente ---
        if rules.get("require_audio", False):
            has_audio = ffprobe.get_audio_stream(source) is not None
            checks.append(
                {
                    "name": "audio",
                    "status": "PASS" if has_audio else "FAIL",
                    "actual": has_audio,
                    "expected": True,
                }
            )

        # --- Codec de vídeo ---
        codec = rules.get("codec")
        if codec:
            stream = ffprobe.get_video_stream(source)
            actual_codec = stream.get("codec_name") if stream else None
            ok = actual_codec == codec
            checks.append(
                {
                    "name": "codec",
                    "status": "PASS" if ok else "FAIL",
                    "actual": actual_codec,
                    "expected": codec,
                }
            )

        overall = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
        self.logger.info("qa completed", status=overall, checks=len(checks))
        return {"status": overall, "checks": checks}

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
