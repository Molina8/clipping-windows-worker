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
