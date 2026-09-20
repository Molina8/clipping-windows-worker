"""Publish job — milestone 1 YouTube.

Dry-run: no YouTube API. Still moves pending_upload -> uploaded.
Live upload is step 4.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.jobs.base import BaseJob
from app.utils.clip_storage import ClipStorage, ClipStorageError


class PublishJob(BaseJob):
    type = "publish"

    def execute(self) -> dict[str, Any]:
        payload = self.job.payload if isinstance(self.job.payload, dict) else {}
        dry_run = payload.get("dry_run", True)
        platform = payload.get("platform") or "youtube"
        clip_id = payload.get("clip_id")
        campaign_id = payload.get("campaign_id")
        file_path = payload.get("file_path")
        if not clip_id:
            raise ValueError("payload.clip_id is required")
        if campaign_id is None:
            raise ValueError("payload.campaign_id is required")
        if not dry_run:
            raise NotImplementedError(
                "live YouTube upload is step 4; rerun tick without --live"
            )

        dest = self._move_to_uploaded(clip_id=str(clip_id), campaign_id=campaign_id, file_path=file_path)
        fake = f"https://youtube.com/shorts/dry-run-{clip_id}"
        self.logger.info(
            "publish dry-run moved to uploaded",
            clip_id=clip_id,
            platform=platform,
            dest=str(dest),
        )
        return {
            "dry_run": True,
            "source_moved": True,
            "final_path_worker": str(dest),
            "publications": [
                {
                    "platform": platform,
                    "status": "posted",
                    "post_url": fake,
                }
            ],
        }

    def _move_to_uploaded(
        self,
        clip_id: str,
        campaign_id: int | str,
        file_path: str | None,
    ) -> Path:
        storage = ClipStorage(
            storage_root=self.settings.clip_storage_root,
            campaign_id=campaign_id,
        )
        already = storage.path_for(clip_id, "uploaded")
        if already.exists():
            return already
        src: Path | None = Path(file_path) if file_path else None
        if src is None or not src.exists():
            src = storage.path_for(clip_id, "pending_upload")
        if not src.exists():
            raise FileNotFoundError(f"clip not in pending_upload or payload path: {src}")
        try:
            return storage.move(src, clip_id, "uploaded")
        except ClipStorageError as e:
            raise ValueError(str(e)) from e
