"""Tests for the Drive/Docs URL resolver.

Estos tests mockean ``httpx`` para no depender de Google.
Cubren:
- Detección de hosts Drive/Docs.
- Reescritura ``/file/d/<ID>/view`` → ``/uc?export=download&id=<ID>``.
- Reescritura ``/open?id=<ID>`` → ``/uc?export=download&id=<ID>``.
- Reescritura ``/uc?...`` → se quita ``confirm=`` redundante.
- Folder listing: extracción de ``data-id`` y selección por extensión.
- Folder listing sin cookies → ``DriveAuthRequired``.
- Doc scraping: MP4 directo, YouTube embed, link a Drive.
- Doc sin vídeo → ``DriveDocNotVideo``.
- Cookies: prioridad de DRIVE_COOKIES_JSON, DRIVE_COOKIES_FILE, env atajo.
- ``try_with_confirm_token`` extrae token de la página y reintenta.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services import drive_resolver
from app.services.drive_resolver import (
    DriveAssetNotFound,
    DriveAuthRequired,
    DriveDocNotVideo,
    DriveResolverError,
    is_drive_url,
    load_drive_cookies,
    resolve,
    try_with_confirm_token,
)


# Detección de hosts --------------------------------------------------


def test_is_drive_url_true_for_drive_hosts():
    assert is_drive_url("https://drive.google.com/file/d/abc/view")
    assert is_drive_url("https://drive.google.com/drive/folders/abc")
    assert is_drive_url("https://docs.google.com/document/d/abc/edit")
    assert is_drive_url("http://docs.google.com/document/d/abc/edit")


def test_is_drive_url_false_for_other_hosts():
    assert not is_drive_url("https://example.com/file.zip")
    assert not is_drive_url("https://www.youtube.com/watch?v=abc")


# view → uc -----------------------------------------------------------


def test_resolve_file_view_returns_uc_url():
    cookies = {"SID": "abc"}
    result = resolve(
        "https://drive.google.com/file/d/1mQQ5FIc_2Ru0eDj6XNNgPFIld2QDE_u7/view?usp=sharing"
    )
    assert "drive.google.com/uc" in result.url
    assert "export=download" in result.url
    assert "1mQQ5FIc_2Ru0eDj6XNNgPFIld2QDE_u7" in result.url
    assert result.source_pattern == "file_view"


def test_resolve_file_open_returns_uc_url():
    result = resolve("https://drive.google.com/open?id=ABC123DEF456")
    assert "id=ABC123DEF456" in result.url
    assert "export=download" in result.url
    assert result.source_pattern == "file_open"


def test_resolve_file_open_without_id_raises():
    with pytest.raises(DriveAssetNotFound):
        resolve("https://drive.google.com/open")


def test_resolve_uc_url_strips_confirm():
    result = resolve(
        "https://drive.google.com/uc?export=download&id=ABC&confirm=t"
    )
    assert "confirm" not in result.url
    assert "id=ABC" in result.url
    assert result.source_pattern == "file_uc"


# Folder listing ------------------------------------------------------


def test_resolve_folder_without_cookies_raises_auth_required():
    with patch.object(drive_resolver, "load_drive_cookies", return_value={}):
        with pytest.raises(DriveAuthRequired):
            resolve(
                "https://drive.google.com/drive/folders/1ABC?usp=sharing"
            )


def test_resolve_folder_with_cookies_picks_first_asset():
    fake_html = (
        '<div data-id="file-id-1" title="clip-final.mp4"></div>'
        '<div data-id="file-id-2" title="documento.pdf"></div>'
        '<div data-id="file-id-3" title="raw.mov"></div>'
    )
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.text = fake_html

    with patch.object(drive_resolver, "load_drive_cookies", return_value={"SID": "x"}):
        with patch("app.services.drive_resolver.httpx.get", return_value=fake_response):
            # Reusar resolve() para el primer file_view de la lista
            # (este test se centra en el comportamiento folder; el de file_view
            # está cubierto arriba).
            result = resolve(
                "https://drive.google.com/drive/folders/1ABC?usp=sharing"
            )

    assert result.source_pattern == "folder"
    assert "id=file-id-1" in result.url  # primer asset por extensión
    assert result.cookies == {"SID": "x"}


def test_resolve_folder_falls_back_to_first_id_when_no_titles():
    fake_html = '<div data-id="orphan-id-1"></div>'
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.text = fake_html

    with patch.object(drive_resolver, "load_drive_cookies", return_value={"SID": "x"}):
        with patch("app.services.drive_resolver.httpx.get", return_value=fake_response):
            result = resolve(
                "https://drive.google.com/drive/u/1/folders/1ABC?usp=sharing"
            )

    assert "id=orphan-id-1" in result.url


def test_resolve_folder_with_login_page_raises_auth_required():
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.text = "<!DOCTYPE html><html>Sign in to continue</html>"

    with patch.object(drive_resolver, "load_drive_cookies", return_value={"SID": "x"}):
        with patch("app.services.drive_resolver.httpx.get", return_value=fake_response):
            with pytest.raises(DriveAuthRequired):
                resolve("https://drive.google.com/drive/folders/1ABC")


def test_resolve_folder_empty_raises_not_found():
    # HTML sin data-id: NO es página de login (no contiene "Sign in"),
    # pero tampoco tiene items listables.
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.text = "<html><body>Esta carpeta está vacía.</body></html>"

    with patch.object(drive_resolver, "load_drive_cookies", return_value={"SID": "x"}):
        with patch("app.services.drive_resolver.httpx.get", return_value=fake_response):
            with pytest.raises(DriveAssetNotFound):
                resolve("https://drive.google.com/drive/folders/1ABC")


# Docs scraping -------------------------------------------------------


def test_resolve_doc_extracts_direct_mp4():
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.text = (
        "<html><body>blah "
        "<a href='https://storage.googleapis.com/mi-video.mp4'>link</a>"
        " more text</body></html>"
    )

    with patch.object(drive_resolver, "load_drive_cookies", return_value={}):
        with patch("app.services.drive_resolver.httpx.get", return_value=fake_response):
            result = resolve("https://docs.google.com/document/d/18wyNe5/edit")

    assert result.source_pattern == "doc_video"
    assert result.url == "https://storage.googleapis.com/mi-video.mp4"


def test_resolve_doc_extracts_youtube_embed():
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.text = (
        "<html><iframe src='https://www.youtube.com/embed/dQw4w9WgXcQ'></iframe></html>"
    )

    with patch.object(drive_resolver, "load_drive_cookies", return_value={}):
        with patch("app.services.drive_resolver.httpx.get", return_value=fake_response):
            result = resolve("https://docs.google.com/document/d/DOCID/edit")

    assert "youtube.com/watch?v=dQw4w9WgXcQ" in result.url
    assert result.source_pattern == "doc_video"


def test_resolve_doc_extracts_drive_link():
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.text = (
        "<html><a href='https://drive.google.com/file/d/DRIVE_FILE_ID/view'>ver</a></html>"
    )

    with patch.object(drive_resolver, "load_drive_cookies", return_value={"SID": "x"}):
        with patch("app.services.drive_resolver.httpx.get", return_value=fake_response):
            result = resolve("https://docs.google.com/document/d/DOCID/edit")

    assert "id=DRIVE_FILE_ID" in result.url
    assert result.source_pattern == "file_view"


def test_resolve_doc_without_video_raises_not_video():
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.text = "<html><body>Solo texto, ningún vídeo.</body></html>"

    with patch.object(drive_resolver, "load_drive_cookies", return_value={}):
        with patch("app.services.drive_resolver.httpx.get", return_value=fake_response):
            with pytest.raises(DriveDocNotVideo):
                resolve("https://docs.google.com/document/d/DOCID/edit")


# Cookies --------------------------------------------------------------


def test_load_drive_cookies_from_env_json(monkeypatch):
    payload = json.dumps([{"name": "SID", "value": "abc"}])
    monkeypatch.setenv("DRIVE_COOKIES_JSON", payload)
    assert load_drive_cookies() == {"SID": "abc"}


def test_load_drive_cookies_from_env_file(monkeypatch, tmp_path):
    f = tmp_path / "session.json"
    f.write_text(json.dumps({"SID": "fromfile"}), encoding="utf-8")
    monkeypatch.setenv("DRIVE_COOKIES_FILE", str(f))
    monkeypatch.delenv("DRIVE_COOKIES_JSON", raising=False)
    assert load_drive_cookies() == {"SID": "fromfile"}


def test_load_drive_cookies_env_shortcuts(monkeypatch):
    monkeypatch.delenv("DRIVE_COOKIES_JSON", raising=False)
    monkeypatch.delenv("DRIVE_COOKIES_FILE", raising=False)
    monkeypatch.setenv("DRIVE_SID", "sidval")
    monkeypatch.setenv("DRIVE_HSID", "hsidval")
    assert load_drive_cookies() == {"SID": "sidval", "HSID": "hsidval"}


def test_load_drive_cookies_invalid_json_returns_empty(monkeypatch):
    monkeypatch.setenv("DRIVE_COOKIES_JSON", "not-json")
    assert load_drive_cookies() == {}


def test_load_drive_cookies_empty_when_nothing_set(monkeypatch):
    for var in ("DRIVE_COOKIES_JSON", "DRIVE_COOKIES_FILE",
                "DRIVE_SID", "DRIVE_HSID", "DRIVE_SSID", "DRIVE_LSAP"):
        monkeypatch.delenv(var, raising=False)
    assert load_drive_cookies() == {}


# Confirm-token retry -------------------------------------------------


def test_try_with_confirm_token_extracts_token_and_reissues():
    body = (
        "<html><body>can't scan for viruses, "
        'download anyway? <a href="/uc?export=download&id=X&confirm=TOK123">'
        "click here</a></body></html>"
    )
    first = MagicMock(spec=httpx.Response)
    first.status_code = 200
    first.request = MagicMock()
    first.request.url = "https://drive.google.com/uc?export=download&id=X"
    first.text = body

    retry_response = MagicMock(spec=httpx.Response)
    retry_response.status_code = 200
    retry_response.content = b"\x00\x00\x00\x20ftypisom...BINARY..."

    fake_client = MagicMock()
    fake_client.get.return_value = retry_response
    fake_client.__enter__ = lambda self: self
    fake_client.__exit__ = lambda self, *a: None

    with patch("app.services.drive_resolver.httpx.Client", return_value=fake_client):
        out = try_with_confirm_token(first, cookies={"SID": "x"})

    assert out is retry_response
    fake_client.get.assert_called_once()
    called_url = fake_client.get.call_args.args[0]
    assert "confirm=TOK123" in called_url


def test_try_with_confirm_token_returns_none_when_not_a_confirm_page():
    first = MagicMock(spec=httpx.Response)
    first.status_code = 200
    first.text = "<html>Hello, normal page</html>"

    assert try_with_confirm_token(first, cookies=None) is None


def test_try_with_confirm_token_returns_none_when_no_token():
    first = MagicMock(spec=httpx.Response)
    first.status_code = 200
    first.text = (
        "<html>can't scan for viruses but no token here</html>"
    )
    assert try_with_confirm_token(first, cookies=None) is None
