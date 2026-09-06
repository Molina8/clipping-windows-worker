"""Tests de configuración y rutas derivadas."""

from __future__ import annotations

from pathlib import Path

from app.config import Settings


def test_default_settings(tmp_path: Path) -> None:
    settings = Settings(working_directory=str(tmp_path))
    assert settings.worker_id == "windows-worker-01"
    assert settings.max_concurrent_jobs == 1
    assert settings.device == "cuda"
    assert settings.allow_cpu_fallback is False


def test_derived_directories(tmp_path: Path) -> None:
    settings = Settings(working_directory=str(tmp_path))
    assert settings.downloads_dir == tmp_path / "downloads"
    assert settings.jobs_dir == tmp_path / "jobs"
    assert settings.outputs_dir == tmp_path / "outputs"
    assert settings.temp_dir == tmp_path / "temp"
    assert settings.logs_dir == tmp_path / "logs"


def test_ensure_directories_creates_all(tmp_path: Path) -> None:
    settings = Settings(working_directory=str(tmp_path))
    settings.ensure_directories()
    for directory in (
        settings.working_directory,
        settings.downloads_dir,
        settings.jobs_dir,
        settings.outputs_dir,
        settings.temp_dir,
        settings.logs_dir,
    ):
        assert directory.is_dir()


def test_working_directory_expands_user(tmp_path: Path) -> None:
    settings = Settings(working_directory=str(tmp_path))
    assert settings.working_directory == tmp_path
