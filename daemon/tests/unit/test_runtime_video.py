# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

from schoolbookd.content.catalog import CharterReviewer, VideoCatalog
from schoolbookd.content.vetting import VideoCandidate
from schoolbookd.db.engine import make_engine, migrate, session_factory
from schoolbookd.db.store import Store
from schoolbookd.policy.output_check import OutputCheck
from schoolbookd.providers.base import FakeLLM, FakeTTS
from schoolbookd.runtime import LiveState, Runtime
from schoolbookd.tutor.prompts import AgeProfile


class ScriptSearch:
    def __init__(self, videos: list[VideoCandidate]) -> None:
        self.videos = videos

    def search(self, query: str) -> list[VideoCandidate]:
        del query
        return self.videos


def _store(tmp_path: Path) -> Store:
    engine = make_engine(tmp_path / "schoolbook.db")
    migrate(engine)
    store = Store(session_factory(engine))
    store.upsert_learner(learner_id="kid", first_name="Arum", birth_year=2020)
    return store


def _runtime(store: Store, catalog: VideoCatalog | None) -> Runtime:
    return Runtime(
        store=store,
        llm=FakeLLM([]),
        tts=FakeTTS(),
        output_check=OutputCheck([]),
        apps={},
        age_profile=AgeProfile(id="age-6"),
        core_prompt="computer helper",
        catalog=catalog,
    )


def _live(store: Store) -> LiveState:
    session_id = store.start_session("kid", "fake")
    return LiveState(session_id=session_id, learner_id="kid")


def _dinosaur() -> VideoCandidate:
    return VideoCandidate(
        video_id="abcdefghijk",
        title="Dinosaurs for kids",
        channel_id="chan",
        channel_title="Science",
        description="Big lizards from long ago.",
        duration_s=300,
        embeddable=True,
        age_restricted=False,
        live=False,
        short=False,
        language="en",
    )


def test_search_vet_play_marks_the_video_playing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    catalog = VideoCatalog(store, ScriptSearch([_dinosaur()]), CharterReviewer(), CharterReviewer())
    runtime = _runtime(store, catalog)
    live = _live(store)
    search = runtime.run_tool(live, "search_videos", {"query": "dinosaur"})
    candidates = search["candidates"]
    assert isinstance(candidates, list)
    assert candidates[0]["video_id"] == "abcdefghijk"
    vet = runtime.run_tool(live, "vet_video", {"video_id": "abcdefghijk"})
    assert vet["verdict"] == "approved"
    play = runtime.run_tool(live, "play_video", {"video_id": "abcdefghijk"})
    assert play == {"playing": "abcdefghijk"}
    assert live.playing_video == "abcdefghijk"
    assert live.screen == "video"


def test_play_video_without_vet_is_denied(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runtime = _runtime(store, None)
    live = _live(store)
    play = runtime.run_tool(live, "play_video", {"video_id": "notvetted1"})
    assert play == {"error": "video has not passed vetting"}
    assert live.playing_video is None
    assert live.screen == "home"
