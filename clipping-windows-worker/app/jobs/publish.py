"""Publish job — milestone 1 YouTube.

Dry-run (payload.dry_run true, default): no upload, no file move.
Live YouTube upload is step 4.
"""
from __future__ import annotations

from typing import Any

from app.jobs.base import BaseJob


class PublishJob(BaseJob):
    type = "publish"

    def execute(self) -> dict[str, Any]:
        payload = self.job.payload if isinstance(self.job.payload, dict) else {}
        dry_run = payload.get("dry_run", True)
        platform = payload.get("platform") or "youtube"
        clip_id = payload.get("clip_id")
        file_path = payload.get("file_path")
        if not clip_id:
            raise ValueError("payload.clip_id is required")
        if not file_path:
            raise ValueError("payload.file_path is required")
        if not dry_run:
            raise NotImplementedError(
                "live YouTube upload is step 4; rerun tick without --live"
            )
        fake = f"https://youtube.com/shorts/dry-run-{clip_id}"
        self.logger.info(
            "publish dry-run (no upload, no move)",
            clip_id=clip_id,
            platform=platform,
            file_path=file_path,
        )
        return {
            "dry_run": True,
            "publications": [
                {
                    "platform": platform,
                    "status": "posted",
                    "post_url": fake,
                }
            ],
        }
