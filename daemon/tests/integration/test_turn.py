# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

from schoolbookd.content.apps import Activity, AppManifest
from schoolbookd.db.engine import make_engine, migrate, session_factory
from schoolbookd.db.models import Skill
from schoolbookd.db.store import Store
from schoolbookd.policy.output_check import OutputCheck
from schoolbookd.providers.base import FakeLLM, FakeTTS, LLMResponse, ToolUse
from schoolbookd.runtime import LiveState, Runtime
from schoolbookd.tutor.prompts import AgeProfile


def _runtime(tmp_path: Path, script: list[LLMResponse]) -> tuple[Runtime, LiveState]:
    database = tmp_path / "schoolbook.db"
    engine = make_engine(database)
    migrate(engine)
    store = Store(session_factory(engine))
    store.upsert_learner(learner_id="kid", first_name="Sam", birth_year=2020)
    store.replace_skills(
        [
            Skill(
                id="math.counting.to20",
                title="Count to 20",
                kid_description="Count things up to 20",
                age_min=4,
                age_max=7,
            )
        ]
    )
    store.add_note("kid", "house", "we're vegetarian", None)
    session_id = store.start_session("kid", "fake")
    app = AppManifest(
        id="gcompris",
        name="GCompris",
        exec=["gcompris-qt", "--enable-kioskmode"],
        activity_arg=["--launch", "{activity}"],
        activities=[Activity(id="enumerate", title="Count", skills=["math.counting.to20"])],
    )
    runtime = Runtime(
        store=store,
        llm=FakeLLM(script),
        tts=FakeTTS(),
        output_check=OutputCheck([]),
        apps={"gcompris": app},
        age_profile=AgeProfile(id="age-6"),
        core_prompt="You are a computer helper. Never pretend to be a person.",
        summary=FakeLLM([LLMResponse(text="Counted sharks. Mixing up six and nine.")]),
    )
    return runtime, LiveState(session_id=session_id, learner_id="kid")


def test_scripted_turn_logs_the_board_and_a_skill(tmp_path: Path) -> None:
    runtime, live = _runtime(
        tmp_path,
        [
            LLMResponse(
                text="Sharks are older than trees. Want to count teeth?",
                tool_calls=[
                    ToolUse(
                        "show_board",
                        {"elements": [{"type": "dots", "count": 3, "emoji": "🦈"}]},
                    ),
                    ToolUse(
                        "record_observation",
                        {
                            "skill_id": "math.counting.to20",
                            "outcome": "correct",
                            "evidence": "counted three sharks",
                        },
                    ),
                ],
            )
        ],
    )
    outcome = runtime.child_turn(live, "Tell me about sharks")
    assert outcome.tool_calls[0].allowed
    assert "Sharks" in " ".join(outcome.sentences)
    audio = runtime.speak(outcome.sentences[0])
    assert len(audio) > 0
    profile = runtime.store.profile_input("kid")
    assert "we're vegetarian" in profile.house_notes
    from schoolbookd.db.models import SkillState

    with runtime.store.session() as db:
        state = db.get(SkillState, ("kid", "math.counting.to20"))
        assert state is not None
        assert state.state == "introduced"


def test_launch_builds_argv_from_the_manifest(tmp_path: Path) -> None:
    runtime, live = _runtime(
        tmp_path,
        [
            LLMResponse(
                text="Let's count.",
                tool_calls=[ToolUse("launch_app", {"app_id": "gcompris", "activity": "enumerate"})],
            )
        ],
    )
    outcome = runtime.child_turn(live, "Can we count?")
    argv = outcome.tool_calls[0].result["argv"]
    assert argv == ["gcompris-qt", "--enable-kioskmode", "--launch", "enumerate"]


def test_parent_can_forget_an_observation(tmp_path: Path) -> None:
    runtime, live = _runtime(
        tmp_path,
        [
            LLMResponse(
                text="Nice counting.",
                tool_calls=[
                    ToolUse(
                        "record_observation",
                        {
                            "skill_id": "math.counting.to20",
                            "outcome": "correct",
                            "evidence": "counted",
                        },
                    )
                ],
            )
        ],
    )
    runtime.child_turn(live, "I counted")
    from sqlalchemy import select

    from schoolbookd.db.models import Observation

    with runtime.store.session() as db:
        observation = db.scalars(select(Observation)).one()
        observation_id = observation.id
    runtime.store.forget("observation", "kid", observation_id)
    assert runtime.store.profile_input("kid").practicing == []
