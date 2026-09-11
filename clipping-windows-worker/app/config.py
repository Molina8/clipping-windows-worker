"""Configuración central del Worker mediante pydantic-settings.

Toda la configuración se lee desde variables de entorno o `.env`.
Nunca se almacenan secretos en el código.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

# Directorio raíz del proyecto.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Configuración tipada del Worker."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --------------------------------------------------------------
    # Identidad
    # --------------------------------------------------------------

    worker_id: str = "windows-worker-01"

    # --------------------------------------------------------------
    # API central
    # --------------------------------------------------------------

    api_base_url: str = "https://internal-api.example.com"

    api_token: str = "CHANGE_ME"

    # --------------------------------------------------------------
    # Polling / heartbeat
    # --------------------------------------------------------------

    poll_interval: float = Field(
        default=5.0,
        ge=1.0,
    )

    heartbeat_interval: float = Field(
        default=30.0,
        ge=1.0,
    )

    # --------------------------------------------------------------
    # Concurrencia
    # --------------------------------------------------------------

    max_concurrent_jobs: int = Field(
        default=1,
        ge=1,
        le=8,
    )

    # --------------------------------------------------------------
    # Directorios
    # --------------------------------------------------------------

    working_directory: Path = (
        PROJECT_ROOT / "data"
    )

    # --------------------------------------------------------------
    # Storage de clips (Step 18 architecture_flow.md)
    # --------------------------------------------------------------

    clip_storage_root: Path = Field(
        default=Path(r"C:\CODIANT\clipping\storage\clips"),
        description=(
            "Carpeta raíz del almacenamiento por campaña. El QA job "
            "copia los clips aprobados a <root>/<campaign_id>/pending_upload/."
        ),
    )

    # --------------------------------------------------------------
    # GPU / WhisperX
    # --------------------------------------------------------------

    device: Literal[
        "cuda",
        "cpu",
    ] = "cuda"

    compute_type: str = "float16"

    allow_cpu_fallback: bool = False

    # --------------------------------------------------------------
    # Limpieza
    # --------------------------------------------------------------

    auto_cleanup: bool = True

    job_retention_hours: float = Field(
        default=24.0,
        ge=0.0,
    )

    # --------------------------------------------------------------
    # Logging
    # --------------------------------------------------------------

    log_level: str = "INFO"

    # --------------------------------------------------------------
    # Herramientas
    # --------------------------------------------------------------

    ffmpeg_path: str | None = None

    ffprobe_path: str | None = None

    # --------------------------------------------------------------
    # Rutas derivadas
    # --------------------------------------------------------------

    @property
    def downloads_dir(self) -> Path:
        return (
            self.working_directory
            / "downloads"
        )

    @property
    def jobs_dir(self) -> Path:
        return (
            self.working_directory
            / "jobs"
        )

    @property
    def outputs_dir(self) -> Path:
        return (
            self.working_directory
            / "outputs"
        )

    @property
    def temp_dir(self) -> Path:
        return (
            self.working_directory
            / "temp"
        )

    @property
    def logs_dir(self) -> Path:
        return (
            self.working_directory
            / "logs"
        )

    @field_validator(
        "working_directory",
        mode="before",
    )
    @classmethod
    def _expand_working_directory(
        cls,
        value: object,
    ) -> object:
        """Expande variables y rutas de usuario."""

        if isinstance(value, str):
            return Path(value).expanduser()

        return value

    def ensure_directories(self) -> None:
        """Crea los directorios necesarios."""

        directories = (
            self.working_directory,
            self.downloads_dir,
            self.jobs_dir,
            self.outputs_dir,
            self.temp_dir,
            self.logs_dir,
        )

        for directory in directories:
            directory.mkdir(
                parents=True,
                exist_ok=True,
            )


def get_settings() -> Settings:
    """Devuelve una instancia cacheada de Settings."""

    if not hasattr(
        get_settings,
        "_cached",
    ):
        get_settings._cached = Settings()  # type: ignore[attr-defined]

    return get_settings._cached  # type: ignore[attr-defined]