"""Detección de información del sistema, GPU y herramientas."""

from __future__ import annotations

import platform
import sys

from app.config import Settings
from app.models.worker import GPUInfo, SystemInfo, ToolsInfo
from app.tools.ffmpeg import FFmpegTool
from app.tools.ffprobe import FFprobeTool
from app.tools.whisperx import WhisperXTool
from app.utils.logging import get_logger

logger = get_logger("system_info")


class SystemInfoService:
    """Recopila información del sistema, GPU y herramientas disponibles."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.ffmpeg = FFmpegTool(settings)
        self.ffprobe = FFprobeTool(settings)
        self.whisperx = WhisperXTool(settings)

    def get_system_info(self) -> SystemInfo:
        """Devuelve información básica del sistema."""
        return SystemInfo(
            os=platform.system(),
            os_version=platform.version(),
            cpu=platform.processor() or None,
            ram_total_gb=self._ram_total_gb(),
            ram_available_gb=self._ram_available_gb(),
            python_version=sys.version.split()[0],
        )

    def get_gpu_info(self) -> GPUInfo:
        """Detecta la GPU NVIDIA y la disponibilidad de CUDA."""
        name = None
        vram = None
        cuda_available = False
        cuda_version = None

        try:
            import torch  # noqa: PLC0415

            logger.info(
                "PyTorch detected",
                torch_version=torch.__version__,
                torch_cuda_version=torch.version.cuda,
            )

            cuda_available = bool(torch.cuda.is_available())

            if cuda_available:
                cuda_version = torch.version.cuda
                device_count = torch.cuda.device_count()
                logger.info("CUDA detected", device_count=device_count)

                if device_count > 0:
                    name = torch.cuda.get_device_name(0)
                    props = torch.cuda.get_device_properties(0)
                    vram = round(props.total_memory / (1024**3), 1)
                    logger.info(
                        "GPU detected",
                        name=name,
                        vram_gb=vram,
                        cuda_version=cuda_version,
                    )
            else:
                logger.warning("PyTorch installed but CUDA is not available")

        except ImportError:
            logger.warning("torch no está instalado; no se puede detectar CUDA")

        if name is None:
            name = self._nvidia_gpu_name()

        return GPUInfo(
            name=name,
            available=cuda_available,
            vram_total_gb=vram,
            cuda_available=cuda_available,
            cuda_version=cuda_version,
        )

    def get_tools_info(self) -> ToolsInfo:
        """Comprueba la disponibilidad de ffmpeg, ffprobe y whisperx."""
        return ToolsInfo(
            ffmpeg=self.ffmpeg.available,
            ffprobe=self.ffprobe.available,
            whisperx=self.whisperx.available,
        )

    @staticmethod
    def _ram_total_gb() -> float | None:
        try:
            import psutil  # noqa: PLC0415
            return round(psutil.virtual_memory().total / (1024**3), 1)
        except ImportError:
            return None

    @staticmethod
    def _ram_available_gb() -> float | None:
        try:
            import psutil  # noqa: PLC0415
            return round(psutil.virtual_memory().available / (1024**3), 1)
        except ImportError:
            return None

    @staticmethod
    def _nvidia_gpu_name() -> str | None:
        try:
            from app.utils.subprocess import run_command  # noqa: PLC0415
            result = run_command(
                [
                    "nvidia-smi",
                    "--query-gpu=name",
                    "--format=csv,noheader",
                ],
                timeout=10,
            )
            lines = [
                line.strip()
                for line in result.stdout.strip().splitlines()
                if line.strip()
            ]
            return lines[0] if lines else None
        except Exception:
            return None
