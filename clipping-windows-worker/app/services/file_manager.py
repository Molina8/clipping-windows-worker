"""Gestión de archivos: descarga con streaming y hashing."""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

from app.config import Settings
from app.utils.logging import get_logger

logger = get_logger("file_manager")

# Tamaño de chunk para streaming (1 MB).
_CHUNK_SIZE = 1024 * 1024


class FileManager:
    """Descarga archivos grandes por streaming y calcula su SHA256."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def download(
        self,
        url: str,
        destination: str | Path,
        *,
        timeout: float = 3600.0,
    ) -> Path:
        """Descarga un archivo por streaming sin cargarlo en memoria.

        Devuelve la ruta del archivo descargado.
        """
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)

        logger.info("downloading file", url=url, destination=str(dest))
        with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
            response.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=_CHUNK_SIZE):
                    f.write(chunk)

        logger.info("download complete", url=url, size=dest.stat().st_size)
        return dest

    @staticmethod
    def sha256(path: str | Path) -> str:
        """Calcula el SHA256 de un archivo por streaming."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def file_size(path: str | Path) -> int:
        """Devuelve el tamaño en bytes de un archivo."""
        return Path(path).stat().st_size
