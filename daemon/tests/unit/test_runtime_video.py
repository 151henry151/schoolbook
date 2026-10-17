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

    def search(self, query: str, **_kwargs: object) -> list[VideoCandidate]:
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
    assert play == {"playing": "abcdefghijk", "audio_only": False}
    song = runtime.run_tool(live, "play_video", {"video_id": "abcdefghijk", "audio_only": True})
    assert song == {"playing": "abcdefghijk", "audio_only": True}
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


def test_familiar_music_tracks_actual_plays_and_survives_restart(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runtime = _runtime(store, None)
    live = _live(store)
    assert runtime.run_tool(live, "play_music", {})["empty"] is True
    for video_id in ("songid11111", "songid22222", "songid33333"):
        runtime.approve_video(video_id, video_id, "music", 1)
    runtime.run_tool(live, "play_video", {"video_id": "songid11111", "audio_only": True})
    assert store.familiar_songs("kid") == []  # A failed load does not count.
    runtime.song_started(live, "songid22222")  # Ignore stale player events.
    assert store.familiar_songs("kid") == []
    runtime.song_started(live, "songid11111")
    runtime.song_started(live, "songid11111")  # Resume must not double-count.
    from sqlalchemy import func, select

    from schoolbookd.db.models import SongPlay

    with store.session() as db:
        assert db.scalar(select(func.count()).select_from(SongPlay)) == 1
    runtime.run_tool(live, "play_video", {"video_id": "songid22222", "audio_only": True})
    runtime.song_started(live, "songid22222")
    runtime.run_tool(live, "play_video", {"video_id": "songid33333"})
    runtime.song_started(live, "songid33333")  # Videos are not songs.
    reopened = Store(session_factory(make_engine(tmp_path / "schoolbook.db")))
    assert set(reopened.familiar_songs("kid")) == {"songid11111", "songid22222"}
    assert reopened.familiar_songs("another-child") == []
    first = runtime.run_tool(live, "play_music", {})
    second = runtime.next_song(live)
    assert second is not None
    assert {first["playing"], second["playing"]} == {"songid11111", "songid22222"}
    assert runtime.next_song(live) is None
    runtime.run_tool(live, "play_music", {})
    store.block_video(live.song_queue[0])
    assert runtime.next_song(live) is None  # Recheck parent blocks before each track.
    assert len(store.familiar_songs("kid")) == 1


def test_named_song_clears_familiar_queue(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runtime = _runtime(store, None)
    live = _live(store)
    for video_id in ("songid11111", "songid22222"):
        runtime.approve_video(video_id, video_id, "music", 1)
        store.record_song_play("kid", video_id)
    runtime.run_tool(live, "play_music", {})
    assert live.song_queue
    runtime.run_tool(live, "play_video", {"video_id": "songid11111", "audio_only": True})
    assert not live.song_queue


def test_video_history_counts_half_watched_and_requires_a_specific_replay_request(tmp_path: Path):
    from dataclasses import replace

    store = _store(tmp_path)
    candidates = [_dinosaur(), replace(_dinosaur(), video_id='newvideo123', title='More dinosaurs')]
    catalog = VideoCatalog(store, ScriptSearch(candidates), CharterReviewer(), CharterReviewer())
    runtime, live = _runtime(store, catalog), _live(store)
    runtime.run_tool(live, 'search_videos', {'query': 'dinosaurs'})
    catalog.vet('abcdefghijk')
    runtime.run_tool(live, 'play_video', {'video_id': 'abcdefghijk'})
    runtime.song_started(live, 'abcdefghijk')
    runtime.video_watched(live, 'abcdefghijk', 149, 300)
    assert store.video_history('kid') == []
    runtime.video_watched(live, 'stalevideo1', 150, 300)
    runtime.video_watched(live, 'abcdefghijk', 1, 2)  # Bogus duration.
    assert store.video_history('kid') == []
    runtime.video_watched(live, 'abcdefghijk', 150, 300)
    runtime.video_watched(live, 'abcdefghijk', 200, 300)
    history = runtime.run_tool(live, 'get_video_history', {})['videos']
    assert history[0]['watch_count'] == 1
    assert store.familiar_songs('kid') == []
    results = runtime.run_tool(live, 'search_videos', {'query': 'dinosaurs'})['candidates']
    assert [v['video_id'] for v in results] == ['newvideo123']
    assert results[0]['watch_count'] == 0
    assert store.video_history('another-child') == []
    assert 'error' in runtime.run_tool(live, 'play_video', {'video_id': 'abcdefghijk'})
    live.child_request = 'Show me a video about dinosaurs'
    assert 'error' in runtime.run_tool(live, 'play_video', {
        'video_id': 'abcdefghijk', 'replay_request': live.child_request})
    live.child_request = 'Show me that video again'
    replay = {'video_id': 'abcdefghijk', 'replay_request': live.child_request}
    results = runtime.run_tool(live, 'search_videos', {
        'query': 'dinosaurs', 'requested_video_id': 'abcdefghijk',
        'replay_request': live.child_request})['candidates']
    assert [v['video_id'] for v in results] == ['abcdefghijk']
    assert results[0]['watch_count'] == 1 and results[0]['last_watched_at']
    assert 'error' not in runtime.run_tool(live, 'play_video', replay)
    assert 'error' in runtime.run_tool(live, 'play_video', replay)  # Permission is consumed.
    runtime.video_watched(live, 'abcdefghijk', 151, 300)
    assert store.video_history('kid')[0]['watch_count'] == 2
    reopened = Store(session_factory(make_engine(tmp_path / 'schoolbook.db')))
    assert reopened.video_history('kid')[0]['watch_count'] == 2
    runtime.run_tool(live, 'play_video', {'video_id': 'abcdefghijk', 'audio_only': True})
    runtime.video_watched(live, 'abcdefghijk', 200, 300)
    assert store.video_history('kid')[0]['watch_count'] == 2


def test_watch_exclusions_survive_restart_include_old_history_and_are_per_learner(tmp_path: Path):
    store = _store(tmp_path)
    runtime, live = _runtime(store, None), _live(store)
    for index in range(35):
        video_id = f'video{index:06d}'
        runtime.approve_video(video_id, f'Animal story {index}', 'channel', 1)
        store.record_video_watch('kid', video_id)
    reopened = Store(session_factory(make_engine(tmp_path / 'schoolbook.db')))
    assert len(reopened.video_history('kid')) == 30
    assert len(reopened.watched_video_ids('kid')) == 35
    runtime = _runtime(reopened, None)
    assert 'error' in runtime.run_tool(live, 'play_video', {'video_id': 'video000000'})
    assert runtime.run_tool(live, 'get_video_history', {'query': 'Animal story 0'})['videos'][0][
        'video_id'] == 'video000000'
    live.child_request = 'Please play Animal story 0'
    assert 'error' not in runtime.run_tool(live, 'play_video', {
        'video_id': 'video000000', 'replay_request': live.child_request})
    store.upsert_learner(learner_id='hannah', first_name='Hannah', birth_year=2022)
    other = LiveState(session_id=store.start_session('hannah', 'fake'), learner_id='hannah')
    assert reopened.watched_video_ids('hannah') == set()
    assert 'error' not in runtime.run_tool(other, 'play_video', {'video_id': 'video000000'})


def test_exhausted_search_and_old_tool_ids_cannot_silently_repeat(tmp_path: Path):
    store = _store(tmp_path)
    catalog = VideoCatalog(store, ScriptSearch([_dinosaur()]), CharterReviewer(), CharterReviewer())
    runtime, live = _runtime(store, catalog), _live(store)
    runtime.run_tool(live, 'search_videos', {'query': 'dinosaurs'})
    catalog.vet('abcdefghijk')
    store.record_video_watch('kid', 'abcdefghijk')
    result = runtime.run_tool(live, 'search_videos', {'query': 'dinosaurs'})
    assert result['candidates'] == [] and 'unseen' in result['message']
    assert 'error' in runtime.run_tool(live, 'play_video', {'video_id': 'abcdefghijk'})
    assert live.playing_video is None
    live.child_request = 'Show me a video about dinosaurs'
    assert 'error' in runtime.run_tool(live, 'search_videos', {
        'query': 'dinosaurs', 'requested_video_id': 'abcdefghijk',
        'replay_request': 'Show me that video again'})
    live.child_request = 'Show me that video again'
    store.block_video('abcdefghijk')
    assert 'error' in runtime.run_tool(live, 'play_video', {
        'video_id': 'abcdefghijk', 'replay_request': live.child_request})


def test_that_video_refers_to_last_played_not_an_older_half_watched_video(tmp_path: Path):
    store = _store(tmp_path)
    runtime, live = _runtime(store, None), _live(store)
    for video_id in ('oldervideo1', 'latestvideo'):
        runtime.approve_video(video_id, video_id, 'channel', 1)
    store.record_video_watch('kid', 'oldervideo1')
    runtime.run_tool(live, 'play_video', {'video_id': 'latestvideo'})
    live.child_request = 'Show me that video again'
    assert 'error' in runtime.run_tool(live, 'play_video', {
        'video_id': 'oldervideo1', 'replay_request': live.child_request})
