# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Serve the child UI on localhost and the parent console on its own port."""

from __future__ import annotations

import threading
from pathlib import Path

import uvicorn
from fastapi.staticfiles import StaticFiles

from schoolbookd.api import child_app, console_app
from schoolbookd.bootstrap import build_host
from schoolbookd.config import SchoolbookConfig, Secrets


def serve(config: SchoolbookConfig, secrets: Secrets) -> None:
    host = build_host(config, secrets)
    child = child_app(host)
    console = console_app(host)
    ui_dir = _static_dir(config.share_dir, "ui")
    console_dir = _static_dir(config.share_dir, "console")
    if ui_dir is not None:
        child.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")
    if console_dir is not None:
        console.mount("/", StaticFiles(directory=console_dir, html=True), name="console")
    console_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": console,
            "host": "0.0.0.0" if config.lan.enabled else "127.0.0.1",
            "port": config.ports.console,
            "log_level": "info",
        },
        daemon=True,
    )
    console_thread.start()
    uvicorn.run(child, host="127.0.0.1", port=config.ports.child, log_level="info")


def _static_dir(share: Path, name: str) -> Path | None:
    dist = share / name / "dist"
    if (dist / "index.html").is_file():
        return dist
    direct = share / name
    if (direct / "index.html").is_file():
        return direct
    return None
