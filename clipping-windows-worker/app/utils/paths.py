"""Utilidades de rutas y gestión de directorios por job.

Cada job tiene su propio directorio aislado:

    data/jobs/<job_id>/
        input/
        temp/
        output/
        logs/
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from app.config import Settings

# Caracteres no seguros para nombres de directorio en Windows.
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_job_id(job_id: str) -> str:
    """Limpia un job_id para usarlo como nombre de directorio seguro."""
    cleaned = _UNSAFE.sub("_", job_id).strip()
    return cleaned or "job"


class JobDirectory:
    """Encapsula la estructura de directorios de un job."""

    def __init__(self, settings: Settings, job_id: str) -> None:
        self.settings = settings
        self.job_id = sanitize_job_id(job_id)
        self.root = settings.jobs_dir / self.job_id
        self.input = self.root / "input"
        self.temp = self.root / "temp"
        self.output = self.root / "output"
        self.logs = self.root / "logs"

    def create(self) -> "JobDirectory":
        """Crea la estructura de directorios del job."""
        for directory in (self.root, self.input, self.temp, self.output, self.logs):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    def cleanup(self) -> None:
        """Elimina el directorio del job por completo."""
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)

    def resolve(self, relative: str) -> Path:
        """Resuelve una ruta relativa dentro del directorio del job."""
        return (self.root / relative).resolve()
