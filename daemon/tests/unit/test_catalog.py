# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

import json
from pathlib import Path

from schoolbookd.content.catalog import CharterReviewer, VideoCatalog, nocookie_embed
from schoolbookd.content.vetting import Review, VideoCandidate
from schoolbookd.db.engine import make_engine, migrate, session_factory
from schoolbookd.db.store import Store


class ScriptSearch:
    def __init__(self, videos: list[VideoCandidate]) -> None:
        self.videos = videos
        self.calls = 0
        self.queries: list[str] = []

    def search(self, query: str, **_kwargs: object) -> list[VideoCandidate]:
        self.queries.append(query)
        self.calls += 1
        return self.videos


class Boom:
    def review(self, video: VideoCandidate) -> Review:
        del video
        raise AssertionError("reviewer ran after a hard-filter failure")


def _store(tmp_path: Path) -> Store:
    engine = make_engine(tmp_path / "schoolbook.db")
    migrate(engine)
    return Store(session_factory(engine))


def _video(**overrides: object) -> VideoCandidate:
    fields: dict[str, object] = {
        "video_id": "abcdefghijk",
        "title": "Volcanoes",
        "channel_id": "chan",
        "channel_title": "Rocks",
        "description": "Lava is hot rock.",
        "duration_s": 300,
        "embeddable": True,
        "age_restricted": False,
        "live": False,
        "short": False,
        "language": "en",
    }
    fields.update(overrides)
    return VideoCandidate(**fields)  # type: ignore[arg-type]


def test_song_search_asks_youtube_for_clean_audio(tmp_path: Path) -> None:
    client = ScriptSearch(
        [
            _video(
                video_id="explicit111",
                title="Astronaut in the Ocean Official Video (Explicit)",
                channel_title="Masked Wolf",
            ),
            _video(
                video_id="cleanaudio1",
                title="Astronaut in the Ocean Official Audio (Clean)",
                channel_title="Masked Wolf - Topic",
            ),
        ]
    )
    catalog = VideoCatalog(_store(tmp_path), client, CharterReviewer(), CharterReviewer())
    results = catalog.search("Astronaut in the Ocean", kind="song")
    assert client.queries
    lowered = client.queries[0].lower()
    assert "astronaut in the ocean" in lowered
    assert "documentary" not in lowered
    assert results[0]["video_id"] == "cleanaudio1"
    assert {item["video_id"] for item in results} == {"cleanaudio1", "explicit111"}


def test_song_search_keeps_a_named_song_when_only_explicit_audio_exists(tmp_path: Path) -> None:
    client = ScriptSearch(
        [
            _video(
                video_id="explicit111",
                title="Astronaut in the Ocean (Explicit) Official Audio",
                channel_title="Masked Wolf - Topic",
            ),
        ]
    )
    catalog = VideoCatalog(_store(tmp_path), client, CharterReviewer(), CharterReviewer())
    results = catalog.search("Astronaut in the Ocean", kind="song")
    assert [item["video_id"] for item in results] == ["explicit111"]
    assert catalog.vet("explicit111")["verdict"] == "approved"


def test_song_search_keeps_a_named_kids_song(tmp_path: Path) -> None:
    client = ScriptSearch(
        [_video(video_id="babyshark11", title="Baby Shark", channel_title="Pinkfong")]
    )
    catalog = VideoCatalog(_store(tmp_path), client, CharterReviewer(), CharterReviewer())
    results = catalog.search("Baby Shark", kind="song")
    assert [item["video_id"] for item in results] == ["babyshark11"]


def test_search_rewrites_toward_stretch_and_drops_baby_videos(tmp_path: Path) -> None:
    client = ScriptSearch(
        [
            _video(video_id="cocomelon11", title="Cocomelon dinosaur song", channel_title="Cocomelon"),
            _video(
                video_id="abcdefghijk",
                title="How dinosaurs lived",
                channel_title="PBS Eons",
                description="Paleontology documentary.",
            ),
        ]
    )
    catalog = VideoCatalog(_store(tmp_path), client, CharterReviewer(), CharterReviewer())
    results = catalog.search("dinosaur")
    assert client.queries
    assert len(client.queries[0]) < 80
    assert "dinosaur" in client.queries[0].lower()
    assert [item["video_id"] for item in results] == ["abcdefghijk"]


def test_search_drops_shorts_and_hides_urls(tmp_path: Path) -> None:
    client = ScriptSearch([_video(), _video(video_id="shortshort1", duration_s=20, short=True)])
    catalog = VideoCatalog(_store(tmp_path), client, CharterReviewer(), CharterReviewer())
    first = catalog.search("volcano")
    assert [item["video_id"] for item in first] == ["abcdefghijk"]
    assert "http" not in json.dumps(first)
    catalog.search("volcano")
    assert client.calls == 1


def test_blocking_a_channel_removes_it_from_the_cached_search(tmp_path: Path) -> None:
    store = _store(tmp_path)
    catalog = VideoCatalog(store, ScriptSearch([_video()]), CharterReviewer(), CharterReviewer())
    assert catalog.search("volcano")
    store.block_channel("chan")
    assert catalog.search("volcano") == []


def test_hard_filter_stops_before_model_review(tmp_path: Path) -> None:
    catalog = VideoCatalog(
        _store(tmp_path),
        ScriptSearch([_video(age_restricted=True, title="surprise fight")]),
        Boom(),
        Boom(),
    )
    catalog.search("shock")
    verdict = catalog.vet("abcdefghijk")
    assert verdict["verdict"] == "rejected"
    assert verdict["stage"] == "hard"


def test_red_team_queries_approve_nothing(tmp_path: Path) -> None:
    videos = [
        _video(video_id="ageageageag", age_restricted=True, title="shock"),
        _video(video_id="surprisesur", title="surprise egg"),
    ]
    catalog = VideoCatalog(_store(tmp_path), ScriptSearch(videos), CharterReviewer(), CharterReviewer())
    approved: list[str] = []
    for query in ("shock", "surprise egg"):
        for candidate in catalog.search(query):
            video_id = str(candidate["video_id"])
            if catalog.vet(video_id)["verdict"] == "approved":
                approved.append(video_id)
    assert approved == []


def test_empty_youtube_hits_are_not_cached(tmp_path: Path) -> None:
    client = ScriptSearch([])
    catalog = VideoCatalog(_store(tmp_path), client, CharterReviewer(), CharterReviewer())
    assert catalog.search("dinosaur") == []
    assert catalog.search("dinosaur") == []
    assert client.calls == 2


def test_empty_search_falls_back_to_an_approved_video(tmp_path: Path) -> None:
    store = _store(tmp_path)
    from schoolbookd.db.models import Video
    from datetime import UTC, datetime

    store.save_video(
        Video(
            id="dktnOPfE7Dc",
            source="youtube",
            source_ref="dktnOPfE7Dc",
            title="Dinosaurs for Kids | Learn about Dinosaur History",
            channel_id="chan",
            channel_title="Science",
            duration_s=554,
            summary="Fossils and extinction.",
            verdict="approved",
            vetted_at=datetime.now(UTC),
            language="en",
        )
    )
    catalog = VideoCatalog(store, ScriptSearch([]), CharterReviewer(), CharterReviewer())
    results = catalog.search("dinosaur")
    assert results[0]["video_id"] == "dktnOPfE7Dc"


def test_embed_uses_the_nocookie_domain() -> None:
    url = nocookie_embed("abcdefghijk")
    assert url.startswith("https://www.youtube-nocookie.com/embed/abcdefghijk")
    assert "rel=0" in url
    assert "controls=0" in url
    assert "autoplay=1" in url
