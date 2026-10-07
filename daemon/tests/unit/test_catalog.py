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

    def search(self, query: str) -> list[VideoCandidate]:
        del query
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


def test_embed_uses_the_nocookie_domain() -> None:
    url = nocookie_embed("abcdefghijk")
    assert url.startswith("https://www.youtube-nocookie.com/embed/abcdefghijk")
    assert "rel=0" in url
    assert "controls=0" in url
