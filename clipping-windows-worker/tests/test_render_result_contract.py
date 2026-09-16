"""Regression: verify the render job emits canonical + alias result fields.

VPS `job_state_transitions.on_render_completed` reads:
    result_data.get("file_path")
    result_data.get("file_size")
    result_data.get("duration_seconds")

The Worker must always emit these keys (canon) plus legacy aliases for
backward compatibility. This test asserts the contract on a real render.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.jobs.render import RenderJob
from app.models.job import Job


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        api_base_url="http://localhost",
        api_token="test",
        worker_id="test-worker",
        working_directory=str(tmp_path),
        output_dir=str(tmp_path / "out"),
    )


def _make_job(job_id: str, payload: dict) -> Job:
    j = MagicMock(spec=Job)
    j.id = job_id
    j.payload = payload
    j.job_type = "render"
    return j


def _make_lavfi_source(out_dir: Path, name: str, duration: int, size: str = "320x240") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    src = out_dir / name
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"testsrc=duration={duration}:size={size}:rate=30",
            "-pix_fmt", "yuv420p", str(src),
        ],
        check=True, capture_output=True,
    )
    return src


def test_render_returns_canonical_and_alias_keys(tmp_path):
    """render.execute() must emit file_path, file_size, duration_seconds AND legacy output_path, size, output_format."""
    settings = _make_settings(tmp_path)
    src = _make_lavfi_source(tmp_path, "src.mp4", duration=10)

    job = _make_job("render-canon", {
        "input_video": str(src),
        "format": "9:16",
        "start_time": 2.0,
        "end_time": 7.0,
    })

    rj = RenderJob(settings=settings, job=job)
    result = rj.execute()

    assert "file_path" in result, f"missing file_path in {list(result)}"
    assert "file_size" in result
    assert "duration_seconds" in result
    assert Path(result["file_path"]).exists()
    assert result["file_size"] > 0
    assert result["duration_seconds"] == pytest.approx(5.0)

    # Aliases
    assert result["output_path"] == result["file_path"]
    assert result["size"] == result["file_size"]
    assert result["output_format"] == "9:16"
    assert result["format"] == "9:16"


def test_render_accepts_legacy_output_format_field(tmp_path):
    """Render must read output_format when format is missing."""
    settings = _make_settings(tmp_path)
    src = _make_lavfi_source(tmp_path, "src_legacy.mp4", duration=1)

    job = _make_job("render-legacy-fmt", {
        "input_video": str(src),
        "output_format": "16:9",
        "start_time": 0.0,
        "end_time": 1.0,
    })

    rj = RenderJob(settings=settings, job=job)
    result = rj.execute()
    assert result["format"] == "16:9"


def _probe_fps(path: Path) -> float:
    """Lee fps del stream de vídeo con ffprobe."""
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=avg_frame_rate,r_frame_rate",
            "-of", "default=nw=1",
            str(path),
        ],
        text=True,
    )
    for line in out.splitlines():
        if line.startswith("avg_frame_rate=") or line.startswith("r_frame_rate="):
            num, _, den = line.split("=", 1)[1].partition("/")
            num_f = float(num)
            den_f = float(den) if den else 1.0
            if den_f == 0:
                continue
            return num_f / den_f
    raise AssertionError(f"could not parse fps from ffprobe output:\n{out}")


def test_render_force_30fps_on_30fps_source(tmp_path):
    """Fuente a 30 fps → salida 30 fps (±0.05)."""
    settings = _make_settings(tmp_path)
    src = _make_lavfi_source(tmp_path, "src_30.mp4", duration=4)

    job = _make_job("render-fps-30", {
        "input_video": str(src),
        "format": "9:16",
        "start_time": 0.0,
        "end_time": 3.0,
    })
    rj = RenderJob(settings=settings, job=job)
    result = rj.execute()

    fps = _probe_fps(Path(result["file_path"]))
    assert fps == pytest.approx(30.0, abs=0.5), (
        f"fps esperado ~30, got {fps}. "
        f"El render debe forzar el framerate de salida con -r 30."
    )


def test_render_force_30fps_on_23976_source(tmp_path):
    """Fuente a 23.976 fps → salida 30 fps tras el -r 30 (no 23.976)."""
    settings = _make_settings(tmp_path)
    # Generamos fuente nativo a 23.976 (rate=24000/1001).
    src_dir = tmp_path / "src_23976"
    src_dir.mkdir(parents=True, exist_ok=True)
    src = src_dir / "src.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "testsrc=duration=5:size=1280x720:rate=24000/1001",
            "-pix_fmt", "yuv420p", str(src),
        ],
        check=True, capture_output=True,
    )

    job = _make_job("render-fps-23976", {
        "input_video": str(src),
        "format": "16:9",
        "start_time": 0.0,
        "end_time": 3.0,
    })
    rj = RenderJob(settings=settings, job=job)
    result = rj.execute()

    # Sanity: el fuente SÍ es 23.976.
    src_fps = _probe_fps(src)
    assert 23.0 <= src_fps <= 24.5, f"fuente no es 23.976 (got {src_fps})"

    out_fps = _probe_fps(Path(result["file_path"]))
    assert out_fps == pytest.approx(30.0, abs=0.5), (
        f"fps esperado ~30 sobre fuente 23.976, got {out_fps}. "
        f"Bug: el render no fuerza -r 30 en el output."
    )


def test_render_payload_fps_override(tmp_path):
    """El payload.fps debe sobrescribir el default de Settings."""
    settings = _make_settings(tmp_path)
    src = _make_lavfi_source(tmp_path, "src_override.mp4", duration=4)

    job = _make_job("render-fps-override", {
        "input_video": str(src),
        "format": "16:9",
        "start_time": 0.0,
        "end_time": 3.0,
        "fps": 60.0,
    })
    rj = RenderJob(settings=settings, job=job)
    result = rj.execute()

    fps = _probe_fps(Path(result["file_path"]))
    assert fps == pytest.approx(60.0, abs=0.5), (
        f"payload.fps=60 ignorado: got {fps}"
    )
    assert result["format"] == "16:9"
    assert result["output_format"] == "16:9"


def test_render_accepts_legacy_start_end_fields(tmp_path):
    """Render must read start/end when start_time/end_time missing."""
    settings = _make_settings(tmp_path)
    src = _make_lavfi_source(tmp_path, "src_legacy_t.mp4", duration=5)

    job = _make_job("render-legacy-t", {
        "input_video": str(src),
        "format": "9:16",
        "start": 1.0,
        "end": 4.0,
    })

    rj = RenderJob(settings=settings, job=job)
    result = rj.execute()
    assert result["duration_seconds"] == pytest.approx(3.0)
