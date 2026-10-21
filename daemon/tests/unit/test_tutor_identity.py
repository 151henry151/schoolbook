# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

from schoolbookd.db.engine import make_engine, migrate, session_factory
from schoolbookd.db.store import Store
from schoolbookd.policy.output_check import OutputCheck
from schoolbookd.policy.tools import ToolPolicy
from schoolbookd.providers.base import FakeLLM, FakeTTS
from schoolbookd.providers.openai_realtime import (
    preferred_tutor_voice,
    normalize_tutor_name,
    spoken_child_instructions,
)
from schoolbookd.runtime import LiveState, Runtime
from schoolbookd.tutor.prompts import AgeProfile


def _store(tmp_path: Path) -> Store:
    engine = make_engine(tmp_path / "schoolbook.db")
    migrate(engine)
    store = Store(session_factory(engine))
    store.upsert_learner(learner_id="kid", first_name="Arum", birth_year=2020)
    return store


def _runtime(tmp_path: Path) -> tuple[Runtime, LiveState]:
    store = _store(tmp_path)
    runtime = Runtime(
        store=store,
        llm=FakeLLM([]),
        tts=FakeTTS(),
        output_check=OutputCheck([]),
        apps={},
        age_profile=AgeProfile(id="age-6"),
        core_prompt="computer helper",
    )
    live = LiveState(session_id=store.start_session("kid", "fake"), learner_id="kid")
    return runtime, live


def test_preferred_tutor_voice_resets_a_stored_voice_to_marin(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.put_setting("tutor_voice", "cedar", actor="test")
    assert preferred_tutor_voice(store) == "marin"
    assert store.get_setting("tutor_voice") == "marin"


def test_normalize_tutor_name_keeps_a_short_first_name() -> None:
    assert normalize_tutor_name("max") == "Max"
    assert normalize_tutor_name("Ms. Robot!!!") == "Ms Robot"
    assert normalize_tutor_name("can I call you Pixel") == "Pixel"
    assert normalize_tutor_name("") is None
    assert normalize_tutor_name("x") is None
    assert normalize_tutor_name("this is a very long made up title") is None
    assert normalize_tutor_name("123 Main Street") is None


def test_policy_allows_a_name_but_not_a_voice_change() -> None:
    from schoolbookd.policy.tools import PolicyContext

    policy = ToolPolicy()
    ctx = PolicyContext()
    assert not policy.check("switch_voice", {}, ctx).allowed
    assert policy.check("set_tutor_name", {"name": "Max"}, ctx).allowed
    assert not policy.check("set_tutor_name", {"name": ""}, ctx).allowed
    assert not policy.check("set_tutor_name", {"name": "x" * 40}, ctx).allowed


def test_switch_voice_is_not_a_runtime_tool(tmp_path: Path) -> None:
    runtime, live = _runtime(tmp_path)
    result = runtime.run_tool(live, "switch_voice", {"hint": "somebody else"})
    assert "error" in result
    assert runtime.store.get_setting("tutor_voice") is None


def test_set_tutor_name_persists_a_clean_name(tmp_path: Path) -> None:
    runtime, live = _runtime(tmp_path)
    result = runtime.run_tool(live, "set_tutor_name", {"name": "pixel"})
    assert result["name"] == "Pixel"
    assert result.get("update_instructions") is True
    assert runtime.store.get_setting("tutor_name") == "Pixel"
    bad = runtime.run_tool(live, "set_tutor_name", {"name": "123 Main Street"})
    assert "error" in bad


def test_spoken_instructions_tell_the_tutor_its_name_and_to_keep_its_voice() -> None:
    text = spoken_child_instructions("charter", "age-6", "Arum", tutor_name="Pixel")
    lowered = text.lower()
    assert "pixel" in lowered
    assert "switch_voice" not in text
    assert "set_tutor_name" in text
    assert "i'm sorry, no, i can't, this is my voice" in lowered
