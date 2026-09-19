"""Job de descarga de archivos.

Tras descargar, el fichero se copia a ``data/downloads/{asset_id}/``
y se reporta duración real con ffprobe.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from app.jobs.base import BaseJob
from app.services.file_manager import FileManager, _needs_ytdlp
from app.tools.ffprobe import FFprobeTool

_KIND_TO_EXT = {
    "mp4": ".mp4",
    "mov": ".mov",
    "mkv": ".mkv",
    "webm": ".webm",
    "avi": ".avi",
    "m4v": ".m4v",
    "video": ".mp4",
    "footage": ".mp4",
}


class DownloadJob(BaseJob):
    type = "download"

    def execute(self) -> dict[str, Any]:
        payload = self.job.payload
        url = payload.get("url")
        if not url:
            raise ValueError("payload.url is required")

        file_manager = FileManager(self.settings)

        if _needs_ytdlp(url):
            destination: Path = self.directory.input
            filename_for_log = "<dir>"
        else:
            filename = f"{self.job.id}.bin"
            destination = self.directory.input / filename
            filename_for_log = filename

        self.logger.info("downloading input", url=url, filename=filename_for_log)
        path = file_manager.download(url, destination)
        stable = self._persist(path, payload)
        size = file_manager.file_size(stable)
        sha256 = file_manager.sha256(stable)

        duration = None
        try:
            duration = FFprobeTool(self.settings).get_duration(stable)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("ffprobe duration failed", path=str(stable), error=str(exc))

        self.logger.info(
            "download verified",
            path=str(stable),
            filename=stable.name,
            size=size,
            duration_seconds=duration,
            sha256=sha256[:16],
        )
        result = {
            "file_path": str(stable),
            "file_size": size,
            "filename": stable.name,
            "size": size,
            "sha256": sha256,
        }
        if duration is not None:
            result["duration_seconds"] = duration
        return result

    def _persist(self, src: Path, payload: dict[str, Any]) -> Path:
        asset_id = str(payload.get("asset_id") or self.job.id)
        dest_dir = self.settings.downloads_dir / asset_id
        dest_dir.mkdir(parents=True, exist_ok=True)

        name = str(payload.get("filename") or "")
        ext = Path(name).suffix.lower() if name else ""
        if ext not in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}:
            kind = str(payload.get("kind") or "").lower().lstrip(".")
            ext = _KIND_TO_EXT.get(kind, src.suffix or ".bin")

        dest = dest_dir / f"source{ext}"
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        return dest
