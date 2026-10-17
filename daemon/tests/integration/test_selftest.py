# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

import os
from pathlib import Path

from schoolbookd.__main__ import main
from schoolbookd.policy.unlock import hash_password


def test_check_config_and_self_test_use_shipped_content(tmp_path: Path) -> None:
    etc = tmp_path / "etc"
    apps = etc / "apps.d"
    apps.mkdir(parents=True)
    for manifest in Path("apps.d").glob("*.yaml"):
        (apps / manifest.name).write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
    (etc / "output-check.txt").write_text(
        Path("packaging/output-check.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (etc / "learner.yaml").write_text(
        "id: kid\nfirst_name: Sam\nbirth_year: 2020\n",
        encoding="utf-8",
    )
    (etc / "secrets.env").write_text(
        "\n".join(
            [
                f"PARENT_PASSWORD_HASH={hash_password('parent-secret')}",
                "CONSOLE_SESSION_SECRET=test-secret",
            ]
        ),
        encoding="utf-8",
    )
    config = tmp_path / "schoolbook.yaml"
    config.write_text(
        "\n".join(
            [
                f"data_dir: {tmp_path / 'data'}",
                f"share_dir: {Path.cwd()}",
                f"etc_dir: {etc}",
                "dev_text_input: true",
                "providers:",
                "  llm: fake",
                "  stt: fake",
                "  tts: fake",
            ]
        ),
        encoding="utf-8",
    )
    assert main(["--config", str(config), "--check-config"]) == 0
    assert main(["--config", str(config), "--self-test"]) == 0
    assert os.path.isfile(tmp_path / "data" / "schoolbook.db")
    assert (tmp_path / "data" / "ui.token").read_text(encoding="utf-8").strip()
