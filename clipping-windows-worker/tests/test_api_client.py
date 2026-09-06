from pathlib import Path

from app.config import Settings
from app.models.job import JobStatus
from app.services.api_client import MockAPIClient


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        worker_id="test-worker",
        api_base_url="mock://test",
        api_token="test-token",
        working_directory=tmp_path,
    )


def test_mock_get_next_job_and_start(tmp_path: Path) -> None:
    client = MockAPIClient(_settings(tmp_path))
    client.enqueue_health()

    job = client.get_next_job()
    assert job is not None
    assert job.type == "health"

    assert client.start_job(job.id) is True


def test_mock_job_heartbeat(tmp_path: Path) -> None:
    client = MockAPIClient(_settings(tmp_path))
    client.enqueue_health()

    job = client.get_next_job()
    assert job is not None

    assert client.start_job(job.id) is True
    assert client.job_heartbeat(job.id) is True


def test_mock_result(tmp_path: Path) -> None:
    client = MockAPIClient(_settings(tmp_path))

    assert client.upload_result(
        "job_1",
        {
            "status": "ok",
            "message": "test",
        },
    ) is True


def test_mock_fail(tmp_path: Path) -> None:
    client = MockAPIClient(_settings(tmp_path))

    assert client.fail_job(
        "job_1",
        "test error",
    ) is True