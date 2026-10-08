# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

from schoolbookd.content.apps import Activity, AppManifest
from schoolbookd.db.engine import make_engine, migrate, session_factory
from schoolbookd.db.store import Store
from schoolbookd.policy.output_check import OutputCheck
from schoolbookd.providers.base import FakeLLM, FakeTTS
from schoolbookd.runtime import LiveState, Runtime
from schoolbookd.tutor.prompts import AgeProfile


def _store(tmp_path: Path) -> Store:
    engine = make_engine(tmp_path / "schoolbook.db")
    migrate(engine)
    store = Store(session_factory(engine))
    store.upsert_learner(learner_id="kid", first_name="Arum", birth_year=2020)
    return store


def _gcompris() -> AppManifest:
    return AppManifest(
        id="gcompris",
        name="GCompris",
        exec=["gcompris-qt", "--enable-kioskmode", "-f"],
        activity_arg=["--launch", "{activity}"],
        activities=[
            Activity(id="enumerate", title="Count the items", skills=["math.counting.to20"], ages=[4, 7]),
            Activity(id="memory", title="Memory cards", ages=[4, 8]),
            Activity(id="maze", title="Maze", ages=[5, 8]),
        ],
    )


def _runtime(tmp_path: Path) -> tuple[Runtime, LiveState, list[list[str]]]:
    store = _store(tmp_path)
    started: list[list[str]] = []
    runtime = Runtime(
        store=store,
        llm=FakeLLM([]),
        tts=FakeTTS(),
        output_check=OutputCheck([]),
        apps={"gcompris": _gcompris()},
        age_profile=AgeProfile(id="age-6"),
        core_prompt="computer helper",
        launcher=lambda argv: started.append(list(argv)) or 42,
    )
    live = LiveState(session_id=store.start_session("kid", "fake"), learner_id="kid")
    return runtime, live, started


def test_list_apps_offers_gcompris_games(tmp_path: Path) -> None:
    runtime, live, _started = _runtime(tmp_path)
    listed = runtime.run_tool(live, "list_apps", {})
    assert listed["apps"] == ["gcompris"]
    titles = {game["title"] for game in listed["games"]}
    assert titles == {"Count the items", "Memory cards", "Maze"}
    assert all(game["app_id"] == "gcompris" for game in listed["games"])
    counting = runtime.run_tool(live, "list_apps", {"subject": "count"})
    assert [game["activity"] for game in counting["games"]] == ["enumerate"]


def test_launch_app_starts_the_chosen_gcompris_game(tmp_path: Path) -> None:
    runtime, live, started = _runtime(tmp_path)
    result = runtime.run_tool(live, "launch_app", {"app_id": "gcompris", "activity": "memory"})
    assert result["app_id"] == "gcompris"
    assert result["activity"] == "memory"
    assert result["argv"] == ["gcompris-qt", "--enable-kioskmode", "-f", "--launch", "memory"]
    assert result["pid"] == 42
    assert started == [result["argv"]]
    assert live.screen == "app"
    assert live.app_pid == 42


def test_stop_app_closes_gcompris_and_the_overlay(tmp_path: Path) -> None:
    store = _store(tmp_path)
    started: list[list[str]] = []
    killed: list[int] = []
    overlay: list[object] = []

    def show_overlay(on_close: object) -> object:
        overlay.append("shown")
        return lambda: overlay.append("hidden")

    runtime = Runtime(
        store=store,
        llm=FakeLLM([]),
        tts=FakeTTS(),
        output_check=OutputCheck([]),
        apps={"gcompris": _gcompris()},
        age_profile=AgeProfile(id="age-6"),
        core_prompt="computer helper",
        launcher=lambda argv: started.append(list(argv)) or 42,
        killer=lambda pid: killed.append(pid),
        overlay=show_overlay,
    )
    live = LiveState(session_id=store.start_session("kid", "fake"), learner_id="kid")
    runtime.run_tool(live, "launch_app", {"app_id": "gcompris", "activity": "memory"})
    assert overlay == ["shown"]
    runtime.stop_app(live)
    assert killed == [42]
    assert overlay == ["shown", "hidden"]
    assert live.screen == "home"
    assert live.app_pid is None
