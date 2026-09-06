"""Smoke test del job qa sin pasar por el VPS."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.config import Settings  # noqa: PLC0415
    from app.jobs.qa import QAJob  # noqa: PLC0415
    from app.models.job import Job, JobStatus  # noqa: PLC0415

    settings = Settings()

    payload = {
        "video": str(ROOT / "data" / "jobs" / "test_render_local" / "output" / "clip.mp4"),
        "rules": {
            "min_duration": 9.5,
            "max_duration": 10.5,
            "width": 1920,
            "height": 1080,
            "min_fps": 24,
            "require_audio": True,
            "codec": "h264",
        },
    }

    job = Job(
        id="test_qa_local",
        type="qa",
        status=JobStatus.PROCESSING.value,
        priority=5,
        payload=payload,
    )
    qa_job = QAJob(settings=settings, job=job)
    try:
        result = qa_job.execute()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc!r}")
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
