from __future__ import annotations

import kodoku.cli as cli


def test_main_runs_uvicorn_with_defaults(monkeypatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: calls.update(app=app, **kw))
    monkeypatch.setattr(
        cli, "_open_browser_when_ready", lambda host, port: calls.update(opened=(host, port))
    )

    cli.main(["--port", "9001", "--no-browser"])

    assert calls["app"] == "kodoku.main:app"
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 9001
    assert "opened" not in calls  # --no-browser suppresses it


def test_main_schedules_browser_by_default(monkeypatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: None)
    monkeypatch.setattr(
        cli, "_open_browser_when_ready", lambda host, port: calls.update(opened=(host, port))
    )

    cli.main(["--port", "9002"])

    assert calls["opened"] == ("127.0.0.1", 9002)
