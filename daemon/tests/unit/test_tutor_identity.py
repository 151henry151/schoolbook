# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

from schoolbookd.db.engine import make_engine, migrate, session_factory
from schoolbookd.db.store import Store
from schoolbookd.policy.output_check import OutputCheck
from schoolbookd.policy.tools import ToolPolicy
from schoolbookd.providers.base import FakeLLM, FakeTTS
from schoolbookd.providers.openai_realtime import (
    next_voice,
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


def test_next_voice_cycles_and_honors_boy_or_girl_hints() -> None:
    after_marin = next_voice("marin")
    assert after_marin != "marin"
    assert next_voice(after_marin) != after_marin
    boy = next_voice("marin", "can I talk to a boy")
    assert boy in {"cedar", "ash", "echo", "ballad", "verse"}
    girl = next_voice("cedar", "I want a girl voice")
    assert girl in {"marin", "coral", "shimmer", "sage", "alloy"}
    assert next_voice("marin", "talk to somebody else") != "marin"


def test_normalize_tutor_name_keeps_a_short_first_name() -> None:
    assert normalize_tutor_name("max") == "Max"
    assert normalize_tutor_name("Ms. Robot!!!") == "Ms Robot"
    assert normalize_tutor_name("can I call you Pixel") == "Pixel"
    assert normalize_tutor_name("") is None
    assert normalize_tutor_name("x") is None
    assert normalize_tutor_name("this is a very long made up title") is None
    assert normalize_tutor_name("123 Main Street") is None


def test_policy_allows_spoken_voice_and_name_tools() -> None:
    from schoolbookd.policy.tools import PolicyContext

    policy = ToolPolicy()
    ctx = PolicyContext()
    assert policy.check("switch_voice", {}, ctx).allowed
    assert policy.check("switch_voice", {"hint": "somebody else"}, ctx).allowed
    assert not policy.check("switch_voice", {"hint": "x" * 90}, ctx).allowed
    assert policy.check("set_tutor_name", {"name": "Max"}, ctx).allowed
    assert not policy.check("set_tutor_name", {"name": ""}, ctx).allowed
    assert not policy.check("set_tutor_name", {"name": "x" * 40}, ctx).allowed


def test_switch_voice_persists_the_next_realtime_voice(tmp_path: Path) -> None:
    runtime, live = _runtime(tmp_path)
    first = runtime.run_tool(live, "switch_voice", {"hint": "somebody else"})
    assert first.get("reconnect") is True
    assert first["voice"] != "marin"
    assert runtime.store.get_setting("tutor_voice") == first["voice"]
    boy = runtime.run_tool(live, "switch_voice", {"hint": "a boy"})
    assert boy["voice"] in {"cedar", "ash", "echo", "ballad", "verse"}


def test_set_tutor_name_persists_a_clean_name(tmp_path: Path) -> None:
    runtime, live = _runtime(tmp_path)
    result = runtime.run_tool(live, "set_tutor_name", {"name": "pixel"})
    assert result["name"] == "Pixel"
    assert result.get("update_instructions") is True
    assert runtime.store.get_setting("tutor_name") == "Pixel"
    bad = runtime.run_tool(live, "set_tutor_name", {"name": "123 Main Street"})
    assert "error" in bad


def test_spoken_instructions_tell_the_tutor_its_name_and_voice_tools() -> None:
    text = spoken_child_instructions("charter", "age-6", "Arum", tutor_name="Pixel")
    lowered = text.lower()
    assert "pixel" in lowered
    assert "switch_voice" in text
    assert "set_tutor_name" in text
    assert "somebody else" in lowered or "different voice" in lowered
