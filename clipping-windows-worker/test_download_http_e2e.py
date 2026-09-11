"""Verifica el nuevo naming del DownloadJob sobre HTTP genérico.

Crea un Settings mínimo, instancia DownloadJob con un payload que contiene
una URL "sucia" (query string y slash), ejecuta el job y comprueba:

1. ``result.data.filename`` == ``<job.id>.bin`` (sin caracteres de URL).
2. El archivo existe y tiene magic bytes ``ftyp`` (MP4 real).
3. ``ffprobe`` lo abre correctamente.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

# Asegurar imports del paquete ``app`` aunque se ejecute como script suelto.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.jobs.download import DownloadJob
from app.models.job import Job


def _build_settings() -> Settings:
    """Settings mínimo que apunta a ``data/`` del workspace del Worker."""
    return Settings(
        api_base_url="http://127.0.0.1:8080",
        api_token="dummy-token-for-offline-test",
        worker_id="windows-gpu-worker-01",
        working_directory=ROOT / "data",
    )


def _fake_job(job_id: str) -> Job:
    """Construye un Job mínimo con el payload que llega del VPS."""
    return Job(
        id=job_id,
        type="download",
        status="processing",
        payload={"url": "http://127.0.0.1:8765/test_video.mp4?token=abc&x=y"},
        priority=5,
    )


def main() -> int:
    settings = _build_settings()
    job_id = str(uuid.uuid4())
    job = _fake_job(job_id)

    handler = DownloadJob(settings, job)
    result = handler.execute()

    print("== result.data ==")
    for k, v in result.items():
        if k == "sha256":
            v = v[:16] + "..."
        print(f"  {k}: {v}")

    # 1) Naming: debe terminar en <job_id>.bin, NO en la URL.
    expected_name = f"{job_id}.bin"
    assert result["filename"] == expected_name, (
        f"filename esperado={expected_name!r} obtenido={result['filename']!r}"
    )
    assert "?" not in result["filename"]
    assert "=" not in result["filename"]
    assert "&" not in result["filename"]

    path = Path(result["file_path"])
    assert path.exists(), f"no existe: {path}"
    assert path.name == expected_name

    # 2) Magic bytes: debe ser MP4 real (``ftyp``).
    head = path.read_bytes()[:12]
    print(f"  magic: {head!r}")
    assert b"ftyp" in head, f"magic bytes no son MP4: {head!r}"

    # 3) ffprobe lo abre.
    probe = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration,format_name",
            "-of", "default=noprint_wrappers=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    print("== ffprobe ==")
    print(probe.stdout.strip())
    if probe.returncode != 0:
        print(probe.stderr.strip(), file=sys.stderr)
        return probe.returncode

    print("\nOK: download HTTP e2e verificado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
