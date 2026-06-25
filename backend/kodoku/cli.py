"""`kodoku` console entry point: start the server and open the browser."""
from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn


def _open_browser_when_ready(host: str, port: int) -> None:
    # ponytail: fixed 1.5s delay instead of polling the port; good enough for a
    # local launch. Switch to a readiness poll if startup ever gets slow.
    shown = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
    url = f"http://{shown}:{port}/"
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="kodoku", description="Run Kodoku locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser")
    args = parser.parse_args(argv)

    if not args.no_browser:
        _open_browser_when_ready(args.host, args.port)
    uvicorn.run("kodoku.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
