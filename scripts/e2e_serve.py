# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Serve the built UIs for Playwright. Ports stay off the design-spec preview."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from schoolbookd.config import load_config, load_secrets
from schoolbookd.policy.unlock import hash_password
from schoolbookd.server import serve

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="schoolbook-e2e-"))
    etc = work / "etc"
    apps = etc / "apps.d"
    apps.mkdir(parents=True)
    for manifest in (ROOT / "apps.d").glob("*.yaml"):
        shutil.copy(manifest, apps / manifest.name)
    shutil.copy(ROOT / "packaging" / "output-check.txt", etc / "output-check.txt")
    (etc / "learner.yaml").write_text("id: kid\nfirst_name: Sam\nbirth_year: 2020\n", encoding="utf-8")
    (etc / "secrets.env").write_text(
        f"PARENT_PASSWORD_HASH={hash_password('parent-secret')}\nCONSOLE_SESSION_SECRET=e2e-secret\n",
        encoding="utf-8",
    )
    config_path = work / "schoolbook.yaml"
    config_path.write_text(
        "\n".join(
            [
                f"data_dir: {work / 'data'}",
                f"share_dir: {ROOT}",
                f"etc_dir: {etc}",
                "dev_text_input: true",
                "ports:",
                "  child: 8875",
                "  console: 8876",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    serve(config, load_secrets(config.secrets_file))


if __name__ == "__main__":
    main()
