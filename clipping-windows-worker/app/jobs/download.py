"""Job de descarga de archivos con streaming y verificación SHA256."""

from __future__ import annotations

from typing import Any

from app.jobs.base import BaseJob
from app.services.file_manager import FileManager


class DownloadJob(BaseJob):
    """Descarga un archivo remoto al directorio del job."""

    type = "download"

    def execute(self) -> dict[str, Any]:
        payload = self.job.payload
        url = payload.get("url")
        filename = payload.get("filename", "download.bin")

        if not url:
            raise ValueError("payload.url is required")

        self.logger.info("downloading input", url=url)

        file_manager = FileManager(self.settings)
        destination = self.directory.input / filename
        path = file_manager.download(url, destination)

        size = file_manager.file_size(path)
        sha256 = file_manager.sha256(path)

        self.logger.info("download verified", size=size, sha256=sha256[:16])
        return {
            "file_path": str(path),
            "filename": filename,
            "size": size,
            "sha256": sha256,
        }
