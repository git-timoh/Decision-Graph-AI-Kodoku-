from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kodoku.web import mount_web


def _make_web(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    (out / "s" / "_").mkdir(parents=True)
    (out / "index.html").write_text("<html>home</html>", encoding="utf-8")
    (out / "s" / "_" / "index.html").write_text("<html>session-shell</html>", encoding="utf-8")
    return out


def test_mount_web_serves_index_and_session_shell(tmp_path: Path, monkeypatch) -> None:
    out = _make_web(tmp_path)
    monkeypatch.setattr("kodoku.web.web_dir", lambda: out)

    app = FastAPI()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    assert mount_web(app) is True
    client = TestClient(app)

    # API route still wins over the static mount
    assert client.get("/healthz").json() == {"status": "ok"}
    # root serves index.html
    assert "home" in client.get("/").text
    # any /s/<id> serves the single client shell
    assert "session-shell" in client.get("/s/abc-123").text


def test_mount_web_noop_without_build(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("kodoku.web.web_dir", lambda: None)
    app = FastAPI()
    assert mount_web(app) is False
