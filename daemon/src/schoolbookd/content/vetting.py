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
) -> HardFilterResult:
    if video.video_id in rejected_ids:
        return HardFilterResult(False, "already rejected")
    if not video.embeddable:
        return HardFilterResult(False, "not embeddable")
    if video.age_restricted:
        return HardFilterResult(False, "age restricted")
    if video.live:
        return HardFilterResult(False, "live stream")
    if video.short:
        return HardFilterResult(False, "short")
    low, high = duration_minutes
    if video.duration_s < low * 60 or video.duration_s > high * 60:
        return HardFilterResult(False, "duration outside the window")
    if video.channel_id in blocked_channels:
        return HardFilterResult(False, "channel blocked")
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
) -> list[VideoCandidate]:
    kept: list[VideoCandidate] = []
    for video in videos:
        result = hard_filter(
            video,
            blocked_channels=blocked_channels,
            rejected_ids=rejected_ids,
            duration_minutes=duration_minutes,
            language=language,
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
) -> Verdict:
    hard = hard_filter(
        video,
        blocked_channels=blocked_channels,
        rejected_ids=rejected_ids,
        duration_minutes=duration_minutes,
        language=language,
    )
    if not hard.ok:
        return Verdict("rejected", hard.reason, None, "hard")
    meta = metadata.review(video)
    if not meta.ok:
        return Verdict("rejected", meta.reason, None, "metadata")
    visual = frames.review(video)
    if not visual.ok:
        return Verdict("rejected", visual.reason, None, "visual")
    return Verdict("approved", meta.reason, visual.level, "level")
