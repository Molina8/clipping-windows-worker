"""Job de descarga de archivos.

Soporta dos modos:
- HTTP(S) genérico → descarga con ``httpx.stream`` (streaming directo).
- YouTube / youtu.be → descarga con ``yt-dlp`` (necesario porque
  ``https://www.youtube.com/watch?v=...`` devuelve la página HTML,
  no el MP4/WebM real).

El enrutamiento se hace dentro de ``FileManager.download``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.jobs.base import BaseJob
from app.services.file_manager import FileManager, _needs_ytdlp


class DownloadJob(BaseJob):
    """Descarga un archivo remoto al directorio del job."""

    type = "download"

    def execute(self) -> dict[str, Any]:
        payload = self.job.payload
        url = payload.get("url")

        if not url:
            raise ValueError("payload.url is required")

        file_manager = FileManager(self.settings)

        # Nombre del fichero destino:
        # - HTTP genérico → ``<job.id>.bin`` (job_id ya saneado por
        #   ``sanitize_job_id``; ``.bin`` porque la extensión real solo se
        #   conoce tras sniffing y no aporta valor: ``ffprobe``/``transcribe``
        #   funcionan igualmente sobre ``.bin``).
        # - YouTube → se pasa el directorio directamente; ``FileManager`` aplica
        #   la plantilla ``%(id)s.%(ext)s`` que respeta la extensión real
        #   tras el merge ``webm → mp4``.
        # Nunca se usa la URL como nombre: trae ``?&=:/`` y rompe MAX_PATH.
        if _needs_ytdlp(url):
            destination: Path = self.directory.input
            filename_for_log = "<dir>"
        else:
            filename = f"{self.job.id}.bin"
            destination = self.directory.input / filename
            filename_for_log = filename

        self.logger.info("downloading input", url=url, filename=filename_for_log)

        path = file_manager.download(url, destination)

        size = file_manager.file_size(path)
        sha256 = file_manager.sha256(path)
        final_filename = path.name

        self.logger.info(
            "download verified",
            path=str(path),
            filename=final_filename,
            size=size,
            sha256=sha256[:16],
        )
        # El VPS consume `file_path`/`file_size`/`duration_seconds` (canónico).
        # Mantenemos `size`/`filename` como aliases para retro-compatibilidad.
        return {
            "file_path": str(path),
            "file_size": size,
            "filename": final_filename,
            "size": size,
            "sha256": sha256,
        }
