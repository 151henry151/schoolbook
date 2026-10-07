# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

import pytest

from schoolbookd.__main__ import main
from schoolbookd.config import ConfigError, load_config


def _write_tree(root: Path) -> Path:
    etc = root / "etc"
    share = root / "share"
    data = root / "data"
    (etc / "apps.d").mkdir(parents=True)
    (share / "prompts").mkdir(parents=True)
    (share / "profiles").mkdir(parents=True)
    (share / "skills").mkdir(parents=True)
    (share / "prompts" / "core.md").write_text("charter", encoding="utf-8")
    (share / "profiles" / "age-6.yaml").write_text("id: age-6\n", encoding="utf-8")
    (share / "skills" / "core.yaml").write_text("skills: []\n", encoding="utf-8")
    (etc / "output-check.txt").write_text("password\n", encoding="utf-8")
    (etc / "apps.d" / "gcompris.yaml").write_text("id: gcompris\n", encoding="utf-8")
    config = root / "schoolbook.yaml"
    config.write_text(
        "\n".join(
            [
                f"data_dir: {data}",
                f"share_dir: {share}",
                f"etc_dir: {etc}",
                "providers:",
                "  llm: fake",
                "  stt: fake",
                "  tts: fake",
            ]
        ),
        encoding="utf-8",
    )
    return config


def test_check_config_accepts_complete_tree(tmp_path: Path) -> None:
    config = _write_tree(tmp_path)
    assert main(["--config", str(config), "--check-config"]) == 0


def test_check_config_rejects_unknown_field(tmp_path: Path) -> None:
    config = _write_tree(tmp_path)
    config.write_text(config.read_text(encoding="utf-8") + "browser: firefox\n", encoding="utf-8")
    assert main(["--config", str(config), "--check-config"]) == 1


def test_check_config_names_missing_prompt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = _write_tree(tmp_path)
    loaded = load_config(config_path)
    loaded.core_prompt.unlink()
    code = main(["--config", str(config_path), "--check-config"])
    assert code == 1
    assert "core.md" in capsys.readouterr().err


def test_malformed_yaml_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("providers: [\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(path)


def test_relative_paths_resolve_against_the_config_file(tmp_path: Path) -> None:
    config = _write_tree(tmp_path)
    text = config.read_text(encoding="utf-8")
    text = text.replace(str(tmp_path / "data"), "data")
    config.write_text(text, encoding="utf-8")
    loaded = load_config(config)
    assert loaded.data_dir == (tmp_path / "data").resolve()
