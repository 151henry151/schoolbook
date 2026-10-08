# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""YouTube candidate filters and the vetting pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VideoCandidate:
    video_id: str
    title: str
    channel_id: str
    channel_title: str
    description: str
    duration_s: int
    embeddable: bool
    age_restricted: bool
    live: bool
    short: bool
    language: str
    made_for_kids: bool = False
    tags: list[str] = field(default_factory=list)


_BABY_MARKERS = (
    "cocomelon",
    "baby shark",
    "nursery rhyme",
    "nursery rhymes",
    "little baby bum",
    "super simple songs",
    "ms. rachel",
    "ms rachel",
    "pinkfong",
    "surprise egg",
    "learn colors",
    "learn colours",
    "abc song",
    "phonics song",
    "baby songs",
    "kids songs",
    "for toddlers",
    "for babies",
    "peppa pig",
    "blippi",
)

_STRETCH_BOOST = (
    "documentary",
    "explainer",
    "explained",
    "paleontology",
    "science",
    "how ",
    "why ",
    "pbs",
    "national geographic",
    "khan",
    "crash course",
    "ted-ed",
    "eons",
    "scishow",
    "minuteearth",
    "museum",
)


_EXPLICIT_MARKERS = (
    "explicit",
    "uncensored",
    "dirty version",
    "uncut",
    "nsfw",
)

_CLEAN_AUDIO_BOOST = (
    ("official audio", 8),
    ("clean", 10),
    ("radio edit", 8),
    ("lyrics", 3),
)

_MUSIC_VIDEO_PENALTY = (
    ("official video", 6),
    ("music video", 6),
    ("official mv", 6),
)


def song_search_query(query: str) -> str:
    topic = " ".join(query.split())
    if not topic:
        return topic
    words = topic.split()[:8]
    shaped = " ".join(words)
    lowered = shaped.lower()
    extra: list[str] = []
    if "audio" not in lowered:
        extra.append("audio")
    return " ".join([shaped, *extra]).strip()


def is_explicit_track(video: VideoCandidate) -> bool:
    text = f"{video.title} {video.description}".lower()
    return any(marker in text for marker in _EXPLICIT_MARKERS)


def rank_for_clean_audio(videos: list[VideoCandidate]) -> list[VideoCandidate]:
    def score(video: VideoCandidate) -> int:
        text = f"{video.title} {video.channel_title} {video.description}".lower()
        points = 0
        if is_explicit_track(video):
            points -= 8
        if "topic" in video.channel_title.lower():
            points += 4
        for marker, value in _CLEAN_AUDIO_BOOST:
            if marker in text:
                points += value
        for marker, value in _MUSIC_VIDEO_PENALTY:
            if marker in text:
                points -= value
        return points

    return sorted(videos, key=score, reverse=True)


def educational_search_query(query: str) -> str:
    topic = " ".join(query.split())
    if not topic:
        return topic
    words = topic.split()
    lowered = topic.lower()
    if "documentary" in lowered or "explainer" in lowered:
        return " ".join(words[:8])
    return f"{' '.join(words[:6])} documentary"


def is_baby_content(video: VideoCandidate) -> bool:
    text = f"{video.title} {video.channel_title} {video.description}".lower()
    return any(marker in text for marker in _BABY_MARKERS)


def rank_for_stretch(videos: list[VideoCandidate]) -> list[VideoCandidate]:
    def score(video: VideoCandidate) -> int:
        text = f"{video.title} {video.channel_title} {video.description}".lower()
        return sum(1 for marker in _STRETCH_BOOST if marker in text)

    return sorted(videos, key=score, reverse=True)


@dataclass
class HardFilterResult:
    ok: bool
    reason: str


def hard_filter(
    video: VideoCandidate,
    *,
    blocked_channels: set[str],
    rejected_ids: set[str],
    duration_minutes: tuple[int, int] = (1, 30),
    language: str = "en",
    kind: str = "video",
) -> HardFilterResult:
    if video.video_id in rejected_ids:
        return HardFilterResult(False, "already rejected")
    if not video.embeddable:
        return HardFilterResult(False, "not embeddable")
    if video.live:
        return HardFilterResult(False, "live stream")
    if video.channel_id in blocked_channels:
        return HardFilterResult(False, "channel blocked")
    if kind == "song":
        return HardFilterResult(True, "ok")
    if video.age_restricted:
        return HardFilterResult(False, "age restricted")
    if video.short:
        return HardFilterResult(False, "short")
    if is_baby_content(video):
        return HardFilterResult(False, "baby entertainment")
    low, high = duration_minutes
    if video.duration_s < low * 60 or video.duration_s > high * 60:
        return HardFilterResult(False, "duration outside the window")
    if video.language != language:
        return HardFilterResult(False, "language does not match")
    return HardFilterResult(True, "ok")


def visible_to_tutor(
    videos: list[VideoCandidate],
    *,
    blocked_channels: set[str],
    rejected_ids: set[str],
    duration_minutes: tuple[int, int] = (1, 30),
    language: str = "en",
    kind: str = "video",
) -> list[VideoCandidate]:
    kept: list[VideoCandidate] = []
    for video in videos:
        result = hard_filter(
            video,
            blocked_channels=blocked_channels,
            rejected_ids=rejected_ids,
            duration_minutes=duration_minutes,
            language=language,
            kind=kind,
        )
        if result.ok:
            kept.append(video)
    return kept


@dataclass
class Review:
    ok: bool
    reason: str
    level: int = 1


class MetadataReviewer:
    def review(self, video: VideoCandidate) -> Review:
        raise NotImplementedError


class FrameReviewer:
    def review(self, video: VideoCandidate) -> Review:
        raise NotImplementedError


@dataclass
class Verdict:
    verdict: str
    reasons: str
    level: int | None
    stage: str


@dataclass
class ChannelReputation:
    passes: int = 0
    failures: int = 0
    preferred: bool = False
    demoted: bool = False


def update_reputation(current: ChannelReputation, *, passed: bool) -> ChannelReputation:
    if passed:
        passes = current.passes + 1
        return ChannelReputation(
            passes=passes,
            failures=current.failures,
            preferred=passes >= 3 and current.failures == 0,
            demoted=False,
        )
    return ChannelReputation(
        passes=current.passes,
        failures=current.failures + 1,
        preferred=False,
        demoted=True,
    )


def vet_video(
    video: VideoCandidate,
    *,
    metadata: MetadataReviewer,
    frames: FrameReviewer,
    blocked_channels: set[str],
    rejected_ids: set[str],
    duration_minutes: tuple[int, int] = (1, 30),
    language: str = "en",
    kind: str = "video",
) -> Verdict:
    hard = hard_filter(
        video,
        blocked_channels=blocked_channels,
        rejected_ids=rejected_ids,
        duration_minutes=duration_minutes,
        language=language,
        kind=kind,
    )
    if hard.ok and kind == "song":
        return Verdict("approved", "requested song audio", 1, "song")
    if not hard.ok:
        return Verdict("rejected", hard.reason, None, "hard")
    meta = metadata.review(video)
    if not meta.ok:
        return Verdict("rejected", meta.reason, None, "metadata")
    visual = frames.review(video)
    if not visual.ok:
        return Verdict("rejected", visual.reason, None, "visual")
    return Verdict("approved", meta.reason, visual.level, "level")
