# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

from schoolbookd.content.apps import build_argv, load_manifests
from schoolbookd.content.observe import ScreenObserver, average_hash, hash_distance
from schoolbookd.content.vetting import (
    ChannelReputation,
    FrameReviewer,
    MetadataReviewer,
    Review,
    VideoCandidate,
    educational_search_query,
    rank_for_stretch,
    update_reputation,
    vet_video,
    visible_to_tutor,
)


def _video(**overrides: object) -> VideoCandidate:
    data: dict[str, object] = {
        "video_id": "abcdefghijk",
        "title": "Volcanoes",
        "channel_id": "chan",
        "channel_title": "Science for kids",
        "description": "What makes a volcano blow",
        "duration_s": 300,
        "embeddable": True,
        "age_restricted": False,
        "live": False,
        "short": False,
        "language": "en",
    }
    data.update(overrides)
    return VideoCandidate(**data)  # type: ignore[arg-type]


def test_educational_search_query_aims_at_older_kids() -> None:
    query = educational_search_query("dinosaur")
    lowered = query.lower()
    assert "dinosaur" in lowered
    assert "documentary" in lowered or "explainer" in lowered
    assert len(query) < 80
    long_query = "dinosaur facts for kids educational video explanation of fossils and extinction"
    assert len(educational_search_query(long_query)) < 80
    assert educational_search_query("volcano documentary ages 10-12").lower().count("documentary") == 1


def test_visible_to_tutor_drops_baby_entertainment() -> None:
    videos = [
        _video(video_id="cocomelon11", title="Cocomelon Dinosaur Song", channel_title="Cocomelon"),
        _video(
            video_id="abcdefghijk",
            title="How dinosaurs lived",
            channel_title="PBS Eons",
            description="A paleontology explainer for older kids.",
        ),
    ]
    visible = visible_to_tutor(videos, blocked_channels=set(), rejected_ids=set())
    assert [video.video_id for video in visible] == ["abcdefghijk"]


def test_rank_for_stretch_puts_explainers_first() -> None:
    ranked = rank_for_stretch(
        [
            _video(video_id="songsong111", title="Dinosaur kids song", channel_title="Kids TV"),
            _video(
                video_id="abcdefghijk",
                title="How dinosaurs lived: a science documentary",
                channel_title="PBS Eons",
            ),
        ]
    )
    assert ranked[0].video_id == "abcdefghijk"


def test_search_hides_shorts_live_blocked_and_rejected() -> None:
    videos = [
        _video(),
        _video(video_id="short111111", short=True),
        _video(video_id="live1111111", live=True),
        _video(video_id="block111111", channel_id="bad"),
        _video(video_id="reject11111"),
    ]
    visible = visible_to_tutor(videos, blocked_channels={"bad"}, rejected_ids={"reject11111"})
    assert [video.video_id for video in visible] == ["abcdefghijk"]


def test_hard_filter_order_stops_before_the_model() -> None:
    class Boom(MetadataReviewer):
        def review(self, video: VideoCandidate) -> Review:
            raise AssertionError("metadata review should not run")

    class BoomFrames(FrameReviewer):
        def review(self, video: VideoCandidate) -> Review:
            raise AssertionError("frames should not run")

    verdict = vet_video(
        _video(age_restricted=True),
        metadata=Boom(),
        frames=BoomFrames(),
        blocked_channels=set(),
        rejected_ids=set(),
    )
    assert verdict.verdict == "rejected"
    assert verdict.stage == "hard"


def test_metadata_failure_skips_frames() -> None:
    class RejectMeta(MetadataReviewer):
        def review(self, video: VideoCandidate) -> Review:
            return Review(False, "kid-bait")

    class BoomFrames(FrameReviewer):
        def review(self, video: VideoCandidate) -> Review:
            raise AssertionError("frames should not run")

    verdict = vet_video(
        _video(),
        metadata=RejectMeta(),
        frames=BoomFrames(),
        blocked_channels=set(),
        rejected_ids=set(),
    )
    assert verdict.stage == "metadata"


def test_approval_includes_a_level() -> None:
    class OkMeta(MetadataReviewer):
        def review(self, video: VideoCandidate) -> Review:
            return Review(True, "clear science", 4)

    class OkFrames(FrameReviewer):
        def review(self, video: VideoCandidate) -> Review:
            return Review(True, "calm frames", 4)

    verdict = vet_video(
        _video(),
        metadata=OkMeta(),
        frames=OkFrames(),
        blocked_channels=set(),
        rejected_ids=set(),
    )
    assert verdict.verdict == "approved"
    assert verdict.level == 4


def test_one_failure_demotes_a_channel() -> None:
    reputation = update_reputation(ChannelReputation(passes=3, preferred=True), passed=False)
    assert reputation.demoted
    assert not reputation.preferred


def test_argv_comes_from_the_manifest(tmp_path: Path) -> None:
    (tmp_path / "gcompris.yaml").write_text(
        """
id: gcompris
name: GCompris
exec: [gcompris-qt, --enable-kioskmode, -f]
activity_arg: ["--launch", "{activity}"]
level_arg: ["--start-level", "{level}"]
observe: true
activities:
  - id: enumerate
    title: Count the items
    skills: [math.counting.to20]
    ages: [4, 7]
""",
        encoding="utf-8",
    )
    manifest = load_manifests(tmp_path)["gcompris"]
    argv = build_argv(manifest, "enumerate", 2)
    assert argv == [
        "gcompris-qt",
        "--enable-kioskmode",
        "-f",
        "--launch",
        "enumerate",
        "--start-level",
        "2",
    ]


def test_observer_drops_near_duplicate_frames() -> None:
    quiet = bytes([0] * 32 + [255] * 32)
    loud = bytes([255] * 32 + [0] * 32)
    observer = ScreenObserver(interval_s=3, change_threshold=0)
    assert observer.consider(quiet, 8, 8, 0)
    assert not observer.consider(loud, 8, 8, 1)
    assert observer.consider(loud, 8, 8, 3)
    assert hash_distance(average_hash(quiet, 8, 8), average_hash(loud, 8, 8)) > 0
