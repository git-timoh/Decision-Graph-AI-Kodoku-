#!/usr/bin/env python3
"""Build the UI and stage it into the backend package for `pipx install ./backend`.

pipx builds the wheel in an isolated copy of ./backend, so it can't see
../frontend — the UI has to be staged inside the package (kodoku/_web) first.
This does that in one cross-platform step. Run from anywhere; paths are absolute.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DEST = ROOT / "backend" / "kodoku" / "_web"

npm = shutil.which("npm")
if npm is None:
    sys.exit("npm not found — install Node 20+ first")

# Install deps only when the `next` tool is missing — don't `npm ci`, which wipes
# node_modules and fails on Windows/OneDrive when a native binary (next-swc) is
# file-locked. Probe the package dir, not just node_modules (a gutted dir lies).
if not (FRONTEND / "node_modules" / "next").is_dir():
    subprocess.run([npm, "install"], cwd=FRONTEND, check=True)
subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)

if DEST.exists():
    shutil.rmtree(DEST)
shutil.copytree(FRONTEND / "out", DEST)
print(f"Staged UI -> {DEST}\nNext: pipx install ./backend")
