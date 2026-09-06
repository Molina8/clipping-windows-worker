"""Modelos de identidad y estado del worker."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SystemInfo(BaseModel):
    """Información del sistema operativo y hardware."""

    os: str
    os_version: str | None = None
    cpu: str | None = None
    ram_total_gb: float | None = None
    ram_available_gb: float | None = None
    python_version: str | None = None


class GPUInfo(BaseModel):
    """Información de la GPU detectada."""

    name: str | None = None
    available: bool = False
    vram_total_gb: float | None = None
    cuda_available: bool = False
    cuda_version: str | None = None


class ToolsInfo(BaseModel):
    """Disponibilidad de las herramientas externas."""

    ffmpeg: bool = False
    ffprobe: bool = False
    whisperx: bool = False


class WorkerRegistration(BaseModel):
    """Payload enviado al registrar el worker en la API."""

    worker_id: str
    system: SystemInfo
    gpu: GPUInfo
    tools: ToolsInfo
    capabilities: list[str] = Field(default_factory=list)


class Heartbeat(BaseModel):
    """Payload del heartbeat periódico."""

    worker_id: str
    status: str = "online"
    current_job: str | None = None
    gpu: dict[str, Any] = Field(default_factory=dict)
    system: dict[str, Any] = Field(default_factory=dict)
