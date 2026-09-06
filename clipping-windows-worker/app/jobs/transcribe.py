"""Job de transcripción con WhisperX + GPU."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.jobs.base import BaseJob
from app.tools.ffmpeg import FFmpegTool
from app.tools.whisperx import WhisperXTool


class TranscribeJob(BaseJob):
    """Transcribe un vídeo/audio y guarda transcript.json."""

    type = "transcribe"

    def execute(self) -> dict[str, Any]:
        payload = self.job.payload
        # Aceptar `video_path` (contrato interno del Worker) y `video`
        # (contrato del VPS / OpenClaw). Priorizar `video_path` si llega.
        video_path = payload.get("video_path") or payload.get("video")
        language = payload.get("language", "auto")
        diarization = bool(payload.get("diarization", False))

        if not video_path:
            raise ValueError("payload.video_path or payload.video is required")

        # Resolver la ruta: puede ser absoluta o relativa al job.
        source = self._resolve_input(video_path)
        if not source.exists():
            raise FileNotFoundError(f"Input video not found: {source}")

        self.logger.info("extracting audio", video=str(source))
        ffmpeg = FFmpegTool(self.settings)
        audio_path = self.directory.temp / "audio.wav"
        ffmpeg.extract_audio(source, audio_path)

        self.logger.info("starting whisperx", language=language, diarization=diarization)
        whisperx = WhisperXTool(self.settings)
        result = whisperx.transcribe(
            audio_path,
            language=None if language == "auto" else language,
            diarization=diarization,
        )

        # Guardar transcript.json en el directorio de salida.
        transcript_path = self.directory.output / "transcript.json"
        transcript_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        self.logger.info(
            "transcription completed",
            language=result.get("language"),
            segments=len(result.get("segments", [])),
        )
        return {
            "transcript_path": str(transcript_path),
            "language": result.get("language"),
            "duration": result.get("duration"),
            "segments": result.get("segments", []),
            "words": result.get("words", []),
        }

    def _resolve_input(self, video_path: str) -> Path:
        """Resuelve una ruta de entrada, absoluta o relativa al job."""
        path = Path(video_path)
        if path.is_absolute():
            return path
        # Relativa: buscar en input/ del job y en el directorio raíz.
        candidates = [
            self.directory.input / path,
            self.directory.root / path,
            Path(self.settings.working_directory) / path,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]
