# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

import pytest

from schoolbookd.launch import LaunchError, build_plan, prepare_runtime, require_ui


def test_prepare_runtime_writes_config_secrets_and_learner(tmp_path: Path) -> None:
    share = Path.cwd()
    config_path = prepare_runtime(tmp_path, share, parent_password="parent-secret")
    text = config_path.read_text(encoding="utf-8")
    assert "share_dir:" in text
    secrets = (tmp_path / "etc" / "secrets.env").read_text(encoding="utf-8")
    assert "PARENT_PASSWORD_HASH=" in secrets
    assert "parent-secret" not in secrets
    learner = (tmp_path / "etc" / "learner.yaml").read_text(encoding="utf-8")
    assert "first_name:" in learner
    assert (tmp_path / "etc" / "apps.d" / "gcompris.yaml").is_file()
    assert (tmp_path / "etc" / "output-check.txt").is_file()


def test_kiosk_plan_wraps_the_session_in_cage() -> None:
    plan = build_plan(
        config_path=Path("/tmp/schoolbook.yaml"),
        url="http://127.0.0.1:8765/?dev=1",
        data_dir=Path("/tmp/data"),
        python="/usr/bin/python3",
        session="schoolbook-session",
        cage="cage",
    )
    assert plan.daemon_cmd[-1] == "serve"
    assert "--config" in plan.daemon_cmd
    assert plan.cage_cmd[0] == "cage"
    assert "-s" not in plan.cage_cmd
    assert plan.cage_cmd[1] == "--"
    assert "kiosk" in plan.cage_cmd
    assert "--url" in plan.cage_cmd
    assert "--data-dir" in plan.cage_cmd


def test_require_ui_refuses_a_missing_child_build(tmp_path: Path) -> None:
    with pytest.raises(LaunchError, match="ui/dist"):
        require_ui(tmp_path)
