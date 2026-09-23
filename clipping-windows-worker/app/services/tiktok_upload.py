"""TikTok Direct Post via Content Posting API. FILE_UPLOAD from local mp4."""
from __future__ import annotations

import time
from pathlib import Path

import httpx

OPEN = "https://open.tiktokapis.com"


def upload_video(
    *,
    file_path: Path,
    title: str,
    access_token: str,
    privacy_level: str = "SELF_ONLY",
) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(str(file_path))
    if not access_token:
        raise RuntimeError("TIKTOK_ACCESS_TOKEN missing")

    size = file_path.stat().st_size
    raw = file_path.read_bytes()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    with httpx.Client(timeout=300.0, follow_redirects=True) as client:
        creator = client.post(
            f"{OPEN}/v2/post/publish/creator_info/query/",
            headers=headers,
        )
        if creator.status_code >= 400:
            raise RuntimeError(f"tiktok creator_info {creator.status_code}: {creator.text[:500]}")
        info = (creator.json() or {}).get("data") or {}
        options = info.get("privacy_level_options") or ["SELF_ONLY"]
        privacy = privacy_level if privacy_level in options else (options[0] if options else "SELF_ONLY")

        init = client.post(
            f"{OPEN}/v2/post/publish/video/init/",
            headers=headers,
            json={
                "post_info": {
                    "title": (title or "")[:150],
                    "privacy_level": privacy,
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                    "video_cover_timestamp_ms": 1000,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": size,
                    "total_chunk_count": 1,
                },
            },
        )
        body = init.json() if init.content else {}
        if init.status_code >= 400 or (body.get("error") or {}).get("code") not in (None, "ok", ""):
            raise RuntimeError(f"tiktok init {init.status_code}: {init.text[:800]}")
        data = body.get("data") or {}
        upload_url = data.get("upload_url")
        publish_id = data.get("publish_id")
        if not upload_url or not publish_id:
            raise RuntimeError(f"tiktok init missing upload_url: {body}")

        put = client.put(
            upload_url,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(size),
                "Content-Range": f"bytes 0-{size - 1}/{size}",
            },
            content=raw,
        )
        if put.status_code not in {200, 201, 206}:
            raise RuntimeError(f"tiktok upload {put.status_code}: {put.text[:500]}")

        status = ""
        for _ in range(40):
            st = client.post(
                f"{OPEN}/v2/post/publish/status/fetch/",
                headers=headers,
                json={"publish_id": publish_id},
            )
            payload = st.json() if st.content else {}
            status = ((payload.get("data") or {}).get("status") or "").upper()
            if status in {"PUBLISH_COMPLETE", "FAILED", "SEND_TO_USER_INBOX"}:
                break
            time.sleep(3)
        if status == "FAILED":
            raise RuntimeError(f"tiktok publish failed: {payload}")
        if status not in {"PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"}:
            raise TimeoutError(f"tiktok status={status} publish_id={publish_id}")

    return {
        "publish_id": publish_id,
        "status": status,
        "privacy_level": privacy,
        "post_url": f"https://www.tiktok.com/@/video/{publish_id}",
    }
