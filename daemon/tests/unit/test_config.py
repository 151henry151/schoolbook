# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

import pytest

from schoolbookd.__main__ import main
from schoolbookd.config import ConfigError, Secrets, explain_startup, load_config


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


def test_realtime_voice_requires_an_openai_key(tmp_path: Path) -> None:
    config = load_config(_write_tree(tmp_path))
    config.providers.voice = "realtime"
    errors = explain_startup(
        config,
        Secrets(parent_password_hash="x", console_session_secret="y"),
    )
    assert any("OPENAI_API_KEY" in item for item in errors)


def test_bootstrap_seeds_hannah_once_and_preserves_parent_edits(tmp_path: Path) -> None:
    from schoolbookd.bootstrap import build_host

    config = load_config(_write_tree(tmp_path))
    (config.etc_dir / "learner.yaml").write_text("id: arum\nfirst_name: Arum\nbirth_year: 2020\n")
    (config.profiles_dir / "age-4.yaml").write_text("id: age-4\nage_years: 4\n")
    (config.profiles_dir / "learners.yaml").write_text(
        "- id: hannah\n  first_name: Hannah\n  birth_year: 2022\n  age_profile: age-4\n")
    (config.apps_dir / "gcompris.yaml").write_text("id: gcompris\nname: GCompris\nexec: [gcompris-qt]\n")
    host = build_host(config, Secrets())
    assert host.learner_id == "arum"
    host.runtime.store.upsert_learner(learner_id="hannah", first_name="Hannah H", birth_year=2021,
                                     age_profile="age-4")
    host.runtime.store.put_setting("active_learner", "hannah")
    rebuilt = build_host(config, Secrets())
    assert rebuilt.learner_id == "hannah"
    assert rebuilt.runtime.store.learner("hannah").first_name == "Hannah H"
    assert len(rebuilt.runtime.store.learners()) == 2
    assert rebuilt.runtime.profile_for("hannah").age_years == 4
