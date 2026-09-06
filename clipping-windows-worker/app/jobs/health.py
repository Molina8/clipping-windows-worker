"""Job de health check: reporta estado del sistema, GPU y herramientas."""

from __future__ import annotations

from typing import Any

from app.jobs.base import BaseJob
from app.services.system_info import SystemInfoService


class HealthJob(BaseJob):
    """Devuelve un snapshot del estado del worker."""

    type = "health"

    def execute(self) -> dict[str, Any]:
        self.logger.info("running health check")
        info = SystemInfoService(self.settings)

        system = info.get_system_info()
        gpu = info.get_gpu_info()
        tools = info.get_tools_info()

        return {
            "status": "ok",
            "worker_id": self.settings.worker_id,
            "system": {
                "os": system.os,
                "os_version": system.os_version,
                "cpu": system.cpu,
                "ram_total_gb": system.ram_total_gb,
                "ram_available_gb": system.ram_available_gb,
                "python_version": system.python_version,
            },
            "gpu": {
                "name": gpu.name,
                "available": gpu.available,
                "vram_total_gb": gpu.vram_total_gb,
                "cuda_available": gpu.cuda_available,
                "cuda_version": gpu.cuda_version,
            },
            "tools": {
                "ffmpeg": tools.ffmpeg,
                "ffprobe": tools.ffprobe,
                "whisperx": tools.whisperx,
            },
        }
