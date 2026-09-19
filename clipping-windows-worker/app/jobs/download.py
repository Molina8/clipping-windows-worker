"""Job de descarga.

Drive grande / Shared Drive → `gog drive download` (OAuth).
HTTP anónimo solo para URLs que no son Drive.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.jobs.base import BaseJob
from app.services.file_manager import FileManager, _needs_ytdlp
from app.tools.ffprobe import FFprobeTool

_KIND_TO_EXT = {
    "mp4": ".mp4",
    "mov": ".mov",
    "mkv": ".mkv",
    "webm": ".webm",
    "avi": ".avi",
    "m4v": ".m4v",
    "video": ".mp4",
    "footage": ".mp4",
}
_FILE_ID_RE = re.compile(r"/file/d/([A-Za-z0-9_-]+)")


def _drive_file_id(url: str) -> str | None:
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    if "drive.google.com" not in host and "docs.google.com" not in host:
        return None
    m = _FILE_ID_RE.search(url)
    if m:
        return m.group(1)
    qs = parse_qs(urlparse(url).query)
    return (qs.get("id") or [None])[0]


def _gog_bin() -> str:
    return os.environ.get("GOG_PATH") or shutil.which("gog") or shutil.which("gog.exe") or ""


def _gog_download(file_id: str, dest: Path, logger) -> Path:
    binary = _gog_bin()
    if not binary:
        raise RuntimeError(
            "gog not found. Install gogcli on the Worker and set GOG_PATH or PATH. "
            "Anonymous Drive HTTP cannot fetch large Shared Drive files."
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [binary, "drive", "download", file_id, "--out", str(dest), "--overwrite"]
    account = os.environ.get("GOG_ACCOUNT")
    if account:
        cmd[1:1] = []  # keep drive as subcommand
        cmd = [binary, "--account", account, "drive", "download", file_id, "--out", str(dest), "--overwrite"]
    env = dict(os.environ)
    logger.info("gog drive download", file_id=file_id, dest=str(dest))
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(
            f"gog download failed ({p.returncode}): {(p.stderr or p.stdout or '')[:500]}"
        )
    if not dest.exists() or dest.stat().st_size < 10_000:
        raise RuntimeError(
            f"gog download produced no media at {dest} size={dest.stat().st_size if dest.exists() else 0}"
        )
    return dest


class DownloadJob(BaseJob):
    type = "download"

    def execute(self) -> dict[str, Any]:
        payload = self.job.payload
        url = payload.get("url")
        if not url:
            raise ValueError("payload.url is required")

        file_manager = FileManager(self.settings)
        drive_id = _drive_file_id(url) or payload.get("source_id") or payload.get("file_id")

        if drive_id and not _needs_ytdlp(url):
            tmp = self.directory.input / f"{self.job.id}.bin"
            path = _gog_download(str(drive_id), tmp, self.logger)
        elif _needs_ytdlp(url):
            path = file_manager.download(url, self.directory.input)
        else:
            path = file_manager.download(url, self.directory.input / f"{self.job.id}.bin")

        stable = self._persist(path, payload)
        size = file_manager.file_size(stable)
        sha256 = file_manager.sha256(stable)
        duration = None
        try:
            duration = FFprobeTool(self.settings).get_duration(stable)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("ffprobe duration failed", path=str(stable), error=str(exc))

        result = {
            "file_path": str(stable),
            "file_size": size,
            "filename": stable.name,
            "size": size,
            "sha256": sha256,
        }
        if duration is not None:
            result["duration_seconds"] = duration
        self.logger.info("download verified", **{k: result[k] for k in ("file_path", "file_size")})
        return result

    def _persist(self, src: Path, payload: dict[str, Any]) -> Path:
        asset_id = str(payload.get("asset_id") or self.job.id)
        dest_dir = self.settings.downloads_dir / asset_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = str(payload.get("filename") or "")
        ext = Path(name).suffix.lower() if name else ""
        if ext not in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}:
            kind = str(payload.get("kind") or "").lower().lstrip(".")
            ext = _KIND_TO_EXT.get(kind, src.suffix or ".bin")
        dest = dest_dir / f"source{ext}"
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        return dest
