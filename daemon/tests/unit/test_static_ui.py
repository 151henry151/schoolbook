# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from schoolbookd.server import UIStaticFiles


def test_ui_entry_pages_are_not_cached_but_hashed_assets_can_be(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<title>Schoolbook</title>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-build123.js").write_text("const version = 'new';")
    app = FastAPI()
    app.mount("/", UIStaticFiles(directory=tmp_path, html=True))
    with TestClient(app) as client:
        for path in ("/", "/index.html", "/?_schoolbook_start=new"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            conditional = client.get(path, headers={"If-None-Match": response.headers["etag"]})
            assert conditional.status_code == 304
            assert conditional.headers["cache-control"] == "no-store"
        asset = client.get("/assets/index-build123.js")
        assert asset.status_code == 200
        assert "cache-control" not in asset.headers
