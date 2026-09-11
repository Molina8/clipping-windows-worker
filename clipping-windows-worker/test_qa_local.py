"""Smoke test del job qa sin pasar por el VPS."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def _make_payload(video_path: Path, *, with_storage: bool) -> dict:
    """Builds a QA payload optionally including Step 18 storage fields."""
    payload: dict = {
        "video": str(video_path),
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
    if with_storage:
        payload["clip_id"] = str(uuid.uuid4())
        payload["campaign_id"] = 5463
    return payload


def _make_job(payload: dict) -> "Job":  # noqa: F821
    from app.models.job import Job, JobStatus  # noqa: PLC0415

    return Job(
        id="test_qa_local",
        type="qa",
        status=JobStatus.PROCESSING.value,
        priority=5,
        payload=payload,
    )


def main() -> int:
    """Legacy smoke test: QA sin storage (no clip_id)."""
    from app.config import Settings  # noqa: PLC0415
    from app.jobs.qa import QAJob  # noqa: PLC0415

    settings = Settings()
    payload = _make_payload(
        ROOT / "data" / "jobs" / "test_render_local" / "output" / "clip.mp4",
        with_storage=False,
    )
    job = _make_job(payload)
    qa_job = QAJob(settings=settings, job=job)
    try:
        result = qa_job.execute()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc!r}")
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


def main_step18() -> int:
    """Step 18 storage test: QA pass -> clip copied to pending_upload/.

    Usa un clip real generado por test_render_local.py y un
    ``clip_storage_root`` temporal para no contaminar el almacenamiento
    real del Worker.
    """
    from app.config import Settings  # noqa: PLC0415
    from app.jobs.qa import QAJob  # noqa: PLC0415

    source_clip = (
        ROOT / "data" / "jobs" / "test_render_local" / "output" / "clip.mp4"
    )
    if not source_clip.exists():
        print(f"FAIL: source clip not found: {source_clip}")
        print("Run test_render_local.py first to generate it.")
        return 1

    # Storage temporal: NO usar el storage real del Worker.
    with tempfile.TemporaryDirectory(prefix="clip_storage_test_") as tmp:
        tmp_root = Path(tmp)
        clip_uuid = str(uuid.uuid4())
        campaign_id = 9999  # campaña de tests; no debe colisionar con reales

        # Settings override para apuntar al tmp
        settings = Settings(clip_storage_root=tmp_root)

        payload = _make_payload(source_clip, with_storage=True)
        payload["clip_id"] = clip_uuid
        payload["campaign_id"] = campaign_id

        job = _make_job(payload)
        qa_job = QAJob(settings=settings, job=job)

        try:
            result = qa_job.execute()
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: qa raised: {exc!r}")
            return 1

        expected_destination = (
            tmp_root
            / str(campaign_id)
            / "pending_upload"
            / f"{clip_uuid}.mp4"
        )

        # --- Checks ---
        checks = []
        checks.append(
            ("status", result.get("status") == "PASS", result.get("status"))
        )
        checks.append(
            (
                "duration_seconds",
                isinstance(result.get("duration_seconds"), (int, float)),
                result.get("duration_seconds"),
            )
        )
        checks.append(
            (
                "final_path_worker",
                result.get("final_path_worker") == str(expected_destination),
                result.get("final_path_worker"),
            )
        )
        checks.append(
            ("source_moved", result.get("source_moved") is True, result.get("source_moved"))
        )
        checks.append(
            (
                "destination_exists",
                expected_destination.exists(),
                str(expected_destination),
            )
        )
        checks.append(
            (
                "source_intact",
                source_clip.exists(),
                "original deleted!",
            )
        )

        failed = [name for name, ok, _ in checks if not ok]
        print(json.dumps(result, indent=2, ensure_ascii=False))
        for name, ok, value in checks:
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {name}: {value!r}")

        if failed:
            print(f"FAILED checks: {failed}")
            return 1
        return 0


def main_qa_fail_no_copy() -> int:
    """Step 18 negative test: QA FAIL -> NO copy a pending_upload/.

    Garantiza que sólo copiamos cuando QA pasa, no en cualquier caso.
    """
    from app.config import Settings  # noqa: PLC0415
    from app.jobs.qa import QAJob  # noqa: PLC0415

    source_clip = (
        ROOT / "data" / "jobs" / "test_render_local" / "output" / "clip.mp4"
    )
    if not source_clip.exists():
        print(f"FAIL: source clip not found: {source_clip}")
        return 1

    with tempfile.TemporaryDirectory(prefix="clip_storage_test_") as tmp:
        tmp_root = Path(tmp)
        clip_uuid = str(uuid.uuid4())
        campaign_id = 9999

        settings = Settings(clip_storage_root=tmp_root)
        payload = _make_payload(source_clip, with_storage=True)
        # Reglas imposibles -> FAIL garantizado
        payload["rules"]["min_duration"] = 9999.0
        payload["clip_id"] = clip_uuid
        payload["campaign_id"] = campaign_id

        job = _make_job(payload)
        qa_job = QAJob(settings=settings, job=job)
        result = qa_job.execute()

        expected_destination = (
            tmp_root / str(campaign_id) / "pending_upload" / f"{clip_uuid}.mp4"
        )

        checks = []
        checks.append(("status", result["status"] == "FAIL", result["status"]))
        checks.append(
            (
                "no_final_path_worker",
                "final_path_worker" not in result,
                "final_path_worker",
            )
        )
        checks.append(
            (
                "no_copy",
                not expected_destination.exists(),
                "destination should not exist",
            )
        )

        failed = [name for name, ok, _ in checks if not ok]
        for name, ok, value in checks:
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {name}: {value!r}")

        if failed:
            print(f"FAILED checks: {failed}")
            return 1
        return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "legacy":
        raise SystemExit(main())
    if mode == "step18":
        raise SystemExit(main_step18())
    if mode == "fail-no-copy":
        raise SystemExit(main_qa_fail_no_copy())
    # all: legacy + step18 + fail-no-copy
    print(">>> legacy QA smoke")
    rc = main()
    print()
    print(">>> Step 18 storage PASS")
    rc |= main_step18()
    print()
    print(">>> Step 18 QA FAIL no copy")
    rc |= main_qa_fail_no_copy()
    raise SystemExit(rc)
