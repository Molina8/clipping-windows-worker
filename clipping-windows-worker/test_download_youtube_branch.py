"""Verifica la rama YouTube del DownloadJob sin hacer download real.

Mockea ``FileManager.download`` para registrar con qué ``destination``
se invoca según la URL. Esto valida que:

1. Para URL YouTube → ``destination`` es el **directorio** ``<job_dir>/input``
   (no ``<job_dir>/input/<id>.bin``), lo que activa la plantilla
   ``%(id)s.%(ext)s`` interna de yt-dlp.
2. Para URL HTTP genérico → ``destination`` es ``<job_dir>/input/<id>.bin``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.jobs.download import DownloadJob
from app.models.job import Job


def _settings() -> Settings:
    return Settings(
        api_base_url="http://127.0.0.1:8080",
        api_token="dummy",
        worker_id="windows-gpu-worker-01",
        working_directory=ROOT / "data",
    )


def _job(job_id: str, url: str) -> Job:
    return Job(
        id=job_id,
        type="download",
        status="processing",
        payload={"url": url},
        priority=5,
    )


def _run(url: str) -> tuple[str, Path]:
    """Ejecuta DownloadJob con FileManager.download mockeado."""
    captured: dict = {}

    def fake_download(self, u, dest, *, timeout=3600.0):
        captured["url"] = u
        captured["destination"] = dest
        # Devolver una ruta fake para no levantar FileNotFoundError al hashear.
        dest_path = Path(dest) if not isinstance(dest, Path) else dest
        if dest_path.is_dir() or str(dest_path).endswith("input"):
            fake = dest_path / "fake.mp4"
        else:
            fake = dest_path
        fake.parent.mkdir(parents=True, exist_ok=True)
        fake.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 100)
        return fake

    job_id = "test-job-youtube-001"
    handler = DownloadJob(_settings(), _job(job_id, url))
    # Parchar el método download de la clase FileManager; DownloadJob
    # lo instancia internamente dentro de execute().
    with patch("app.jobs.download.FileManager.download", fake_download):
        handler.execute()

    return captured["url"], Path(captured["destination"])


def main() -> int:
    # --- HTTP genérico ---
    url, dest = _run("https://example.com/video.mp4")
    print(f"[HTTP]   url={url}\n         destination={dest}")
    assert dest.is_dir() is False, f"HTTP esperaba archivo, got dir: {dest}"
    assert dest.name.endswith(".bin"), f"HTTP esperaba .bin, got {dest.name}"
    assert "test-job-youtube-001" in dest.name, dest.name

    # --- YouTube ---
    url, dest = _run("https://www.youtube.com/watch?v=be7dKHOK4NQ")
    print(f"[YT]     url={url}\n         destination={dest}")
    assert dest.is_dir(), f"YouTube esperaba directorio, got archivo: {dest}"
    assert dest.name == "input", f"YouTube esperaba /input, got {dest.name}"

    # --- youtu.be ---
    url, dest = _run("https://youtu.be/be7dKHOK4NQ")
    print(f"[youtu]  url={url}\n         destination={dest}")
    assert dest.is_dir(), f"youtu.be esperaba directorio, got archivo: {dest}"

    print("\nOK: branch logic download verificada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
