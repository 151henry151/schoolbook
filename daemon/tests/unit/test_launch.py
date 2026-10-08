# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

import pytest

from schoolbookd.launch import (
    LaunchError,
    build_plan,
    cage_env,
    kiosk_command,
    load_env_file,
    prepare_runtime,
    require_ui,
    should_use_cage,
    upgrade_default_learner,
)


def test_prepare_runtime_writes_config_secrets_and_learner(tmp_path: Path) -> None:
    share = Path.cwd()
    config_path = prepare_runtime(tmp_path, share, parent_password="parent-secret")
    text = config_path.read_text(encoding="utf-8")
    assert "share_dir:" in text
    secrets = (tmp_path / "etc" / "secrets.env").read_text(encoding="utf-8")
    assert "PARENT_PASSWORD_HASH=" in secrets
    assert "parent-secret" not in secrets
    learner = (tmp_path / "etc" / "learner.yaml").read_text(encoding="utf-8")
    assert "first_name: Arum" in learner
    assert "talk_mode: handsfree" in learner
    assert "stt: whisper" in text
    assert "stt: fake" not in text
    assert "tts: fake" not in text
    assert "voice: pipeline" in text


def test_prepare_runtime_selects_realtime_voice_when_openai_key_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    config_path = prepare_runtime(tmp_path, Path.cwd(), parent_password="parent-secret")
    text = config_path.read_text(encoding="utf-8")
    assert "voice: realtime" in text
    secrets = (tmp_path / "etc" / "secrets.env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-test" in secrets
    assert (tmp_path / "etc" / "apps.d" / "gcompris.yaml").is_file()
    assert (tmp_path / "etc" / "output-check.txt").is_file()


def test_prepare_runtime_renames_an_existing_default_learner(tmp_path: Path) -> None:
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "learner.yaml").write_text(
        "id: kid\nfirst_name: Sam\nbirth_year: 2020\ntalk_mode: handsfree\n",
        encoding="utf-8",
    )
    prepare_runtime(tmp_path, Path.cwd(), parent_password="parent-secret")
    assert "first_name: Arum" in (etc / "learner.yaml").read_text(encoding="utf-8")


def test_upgrade_renames_the_shipped_default_learner(tmp_path: Path) -> None:
    path = tmp_path / "learner.yaml"
    path.write_text("id: kid\nfirst_name: Sam\nbirth_year: 2020\ntalk_mode: handsfree\n", encoding="utf-8")
    upgrade_default_learner(path)
    text = path.read_text(encoding="utf-8")
    assert "first_name: Arum" in text
    assert "first_name: Sam" not in text


def test_upgrade_leaves_a_custom_name_alone(tmp_path: Path) -> None:
    path = tmp_path / "learner.yaml"
    path.write_text("id: kid\nfirst_name: Samir\nbirth_year: 2020\n", encoding="utf-8")
    upgrade_default_learner(path)
    assert "first_name: Samir" in path.read_text(encoding="utf-8")


def test_env_file_sets_missing_keys_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("YOUTUBE_API_KEY", "keep-me")
    path = tmp_path / ".env"
    path.write_text("ANTHROPIC_API_KEY=sk-test\nYOUTUBE_API_KEY=ignore\n", encoding="utf-8")
    load_env_file(path)
    assert __import__("os").environ["ANTHROPIC_API_KEY"] == "sk-test"
    assert __import__("os").environ["YOUTUBE_API_KEY"] == "keep-me"


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


def test_cage_env_uses_x11_when_only_display_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    env = cage_env({"DISPLAY": ":0"})
    assert env["WLR_BACKENDS"] == "x11"


def test_cage_env_uses_x11_when_the_wayland_socket_is_missing(tmp_path: Path) -> None:
    env = cage_env(
        {"WAYLAND_DISPLAY": "wayland-9", "DISPLAY": ":0", "XDG_RUNTIME_DIR": str(tmp_path)}
    )
    assert env["WLR_BACKENDS"] == "x11"


def test_cage_env_uses_wayland_when_the_socket_exists(tmp_path: Path) -> None:
    (tmp_path / "wayland-0").touch()
    env = cage_env({"WAYLAND_DISPLAY": "wayland-0", "XDG_RUNTIME_DIR": str(tmp_path)})
    assert env["WLR_BACKENDS"] == "wayland"


def test_desktop_sessions_skip_nested_cage() -> None:
    assert should_use_cage({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}) is False
    assert should_use_cage({"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0"}) is False
    assert should_use_cage({"XDG_SESSION_TYPE": "tty"}) is True
    assert should_use_cage({}) is True
    assert should_use_cage({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0", "SCHOOLBOOK_FORCE_CAGE": "1"}) is True


def test_kiosk_command_falls_back_to_the_session_without_cage() -> None:
    argv = kiosk_command(
        session="/usr/bin/schoolbook-session",
        url="http://127.0.0.1:8765/",
        data_dir=Path("/tmp/data"),
        cage=None,
    )
    assert argv[0] == "/usr/bin/schoolbook-session"
    assert "kiosk" in argv
    assert "cage" not in argv


def test_require_ui_refuses_a_missing_child_build(tmp_path: Path) -> None:
    with pytest.raises(LaunchError, match="ui/dist"):
        require_ui(tmp_path)
