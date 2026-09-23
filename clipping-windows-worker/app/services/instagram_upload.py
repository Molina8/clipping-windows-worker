"""Instagram Reels via Graph API resumable upload. Tokens from Worker .env."""
from __future__ import annotations

import time
from pathlib import Path

import httpx

GRAPH = "https://graph.facebook.com"
API_VERSION = "v21.0"


def upload_reel(
    *,
    file_path: Path,
    caption: str,
    access_token: str,
    ig_user_id: str,
) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(str(file_path))
    if not access_token or not ig_user_id:
        raise RuntimeError("INSTAGRAM_ACCESS_TOKEN / INSTAGRAM_IG_USER_ID missing")

    size = file_path.stat().st_size
    headers_auth = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=120.0) as client:
        create = client.post(
            f"{GRAPH}/{API_VERSION}/{ig_user_id}/media",
            headers=headers_auth,
            json={
                "media_type": "REELS",
                "upload_type": "resumable",
                "caption": (caption or "")[:2200],
                "share_to_feed": True,
            },
        )
        create.raise_for_status()
        created = create.json()
        container_id = created.get("id")
        uri = created.get("uri") or (
            f"https://rupload.facebook.com/ig-api-upload/{API_VERSION}/{container_id}"
        )
        if not container_id:
            raise RuntimeError(f"instagram container missing id: {created}")

        raw = file_path.read_bytes()
        up = client.post(
            uri,
            headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(size),
                "Content-Type": "application/octet-stream",
            },
            content=raw,
        )
        up.raise_for_status()

        status_code = "IN_PROGRESS"
        for _ in range(40):
            st = client.get(
                f"{GRAPH}/{API_VERSION}/{container_id}",
                headers=headers_auth,
                params={"fields": "status_code,status"},
            )
            st.raise_for_status()
            status_code = (st.json().get("status_code") or "").upper()
            if status_code in {"FINISHED", "PUBLISHED"}:
                break
            if status_code in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"instagram container {status_code}: {st.json()}")
            time.sleep(3)
        if status_code not in {"FINISHED", "PUBLISHED"}:
            raise TimeoutError(f"instagram container not ready: {status_code}")

        if status_code != "PUBLISHED":
            pub = client.post(
                f"{GRAPH}/{API_VERSION}/{ig_user_id}/media_publish",
                headers=headers_auth,
                data={"creation_id": container_id},
            )
            pub.raise_for_status()
            media_id = pub.json().get("id") or container_id
        else:
            media_id = container_id

        permalink = None
        try:
            info = client.get(
                f"{GRAPH}/{API_VERSION}/{media_id}",
                headers=headers_auth,
                params={"fields": "permalink,shortcode"},
            )
            if info.status_code == 200:
                permalink = info.json().get("permalink")
        except httpx.HTTPError:
            permalink = None

    return {
        "media_id": media_id,
        "container_id": container_id,
        "post_url": permalink or f"https://www.instagram.com/reel/{media_id}/",
    }
