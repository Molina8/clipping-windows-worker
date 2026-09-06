"""Smoke test del job render sin pasar por el VPS."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.config import Settings  # noqa: PLC0415
    from app.jobs.render import RenderJob  # noqa: PLC0415
    from app.models.job import Job, JobStatus  # noqa: PLC0415

    settings = Settings()

    payload = json.loads(Path("test_render_payload.json").read_text(encoding="utf-8"))

    job_id = "test_render_local"
    job = Job(
        id=job_id,
        type="render",
        status=JobStatus.PROCESSING.value,
        priority=5,
        payload=payload,
    )

    render_job = RenderJob(settings=settings, job=job)
    try:
        result = render_job.execute()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc!r}")
        return 1
    print("OK")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
