"""Tests de utilidades de rutas y subprocesos."""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.utils.paths import JobDirectory, sanitize_job_id
from app.utils.subprocess import CommandError, run_command


def test_sanitize_job_id() -> None:
    assert sanitize_job_id("job_123") == "job_123"
    assert sanitize_job_id("a/b\\c:d") == "a_b_c_d"
    assert sanitize_job_id("") == "job"


def test_job_directory_structure(tmp_path: Path) -> None:
    settings = Settings(working_directory=str(tmp_path))
    jd = JobDirectory(settings, "job_123").create()
    assert jd.root.is_dir()
    assert jd.input.is_dir()
    assert jd.temp.is_dir()
    assert jd.output.is_dir()
    assert jd.logs.is_dir()


def test_job_directory_cleanup(tmp_path: Path) -> None:
    settings = Settings(working_directory=str(tmp_path))
    jd = JobDirectory(settings, "job_123").create()
    (jd.output / "file.txt").write_text("x")
    jd.cleanup()
    assert not jd.root.exists()


def test_run_command_success() -> None:
    result = run_command(["python", "-c", "print('hello')"])
    assert result.returncode == 0
    assert "hello" in result.stdout


def test_run_command_failure() -> None:
    try:
        run_command(["python", "-c", "import sys; sys.exit(3)"])
        assert False, "should have raised"
    except CommandError as exc:
        assert exc.returncode == 3
