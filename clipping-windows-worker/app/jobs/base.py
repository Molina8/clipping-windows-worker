"""Clase base de los handlers de jobs.

Cada tipo de job implementa `execute()` y devuelve un dict con el resultado.
El framework se encarga de: crear directorios, actualizar estados,
capturar errores y reportar resultados.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.config import Settings
from app.models.job import Job
from app.utils.logging import get_logger
from app.utils.paths import JobDirectory


class BaseJob(ABC):
    """Base para todos los handlers de jobs."""

    #: Nombre del tipo de job (debe coincidir con `job.type`).
    type: str = "base"

    def __init__(self, settings: Settings, job: Job) -> None:
        self.settings = settings
        self.job = job
        self.logger = get_logger(f"job.{self.type}")
        self.directory = JobDirectory(settings, job.id).create()

    @abstractmethod
    def execute(self) -> dict[str, Any]:
        """Ejecuta el job y devuelve el resultado como dict."""
        raise NotImplementedError

    def cleanup(self) -> None:
        """Limpia recursos temporales del job (por defecto no hace nada)."""
        pass
