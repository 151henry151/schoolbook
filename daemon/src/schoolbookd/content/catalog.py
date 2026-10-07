# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Search cache, vetting, and channel reputation. The tutor never receives a URL."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol, cast

from schoolbookd.content.vetting import (
    ChannelReputation,
    FrameReviewer,
    MetadataReviewer,
    Review,
    VideoCandidate,
    update_reputation,
    vet_video,
    visible_to_tutor,
)
from schoolbookd.db.models import Video
from schoolbookd.db.store import Store


class SearchClient(Protocol):
    def search(self, query: str) -> list[VideoCandidate]: ...


class Reviewer(Protocol):
    def review(self, video: VideoCandidate) -> Review: ...


class CharterReviewer:
    """Local stand-in used when no Claude reviewer is configured. It still runs as a stage."""

    def review(self, video: VideoCandidate) -> Review:
        text = f"{video.title} {video.description} {video.channel_title}".lower()
        for word in ("surprise", "buy now", "violent", "clickbait"):
            if word in text:
                return Review(False, word, 1)
        return Review(True, "fits the learner", 4)


def candidate_dict(video: VideoCandidate) -> dict[str, object]:
    return asdict(video)


def candidate_from(raw: object) -> VideoCandidate | None:
    if not isinstance(raw, dict):
        return None
    try:
        tags = raw.get("tags", [])
        return VideoCandidate(
            video_id=str(raw["video_id"]),
            title=str(raw["title"]),
            channel_id=str(raw["channel_id"]),
            channel_title=str(raw["channel_title"]),
            description=str(raw["description"]),
            duration_s=int(str(raw["duration_s"])),
            embeddable=bool(raw["embeddable"]),
            age_restricted=bool(raw["age_restricted"]),
            live=bool(raw["live"]),
            short=bool(raw["short"]),
            language=str(raw["language"]),
            made_for_kids=bool(raw.get("made_for_kids", False)),
            tags=[str(tag) for tag in tags] if isinstance(tags, list) else [],
        )
    except (KeyError, TypeError, ValueError):
        return None


def public_candidate(video: VideoCandidate) -> dict[str, object]:
    return {
        "video_id": video.video_id,
        "title": video.title,
        "channel": video.channel_title,
        "channel_id": video.channel_id,
        "duration_s": video.duration_s,
        "description": video.description,
        "made_for_kids": video.made_for_kids,
    }


class VideoCatalog:
    def __init__(
        self,
        store: Store,
        youtube: SearchClient | None,
        metadata: Reviewer,
        frames: Reviewer,
        *,
        duration_minutes: tuple[int, int] = (1, 30),
        language: str = "en",
    ) -> None:
        self.store = store
        self.youtube = youtube
        self.metadata = metadata
        self.frames = frames
        self.duration_minutes = duration_minutes
        self.language = language

    def search(self, query: str) -> list[dict[str, object]]:
        key = "yt-cache:" + query.strip().lower()
        cached_ids = self.store.get_setting(key)
        candidates = self._load_cached(cached_ids)
        if candidates is None:
            candidates = self.youtube.search(query) if self.youtube is not None else []
            self._remember(key, candidates)
        kept = visible_to_tutor(
            candidates,
            blocked_channels=self.store.blocked_channels(),
            rejected_ids=self.store.rejected_ids(),
            duration_minutes=self.duration_minutes,
            language=self.language,
        )
        return [public_candidate(video) for video in kept]

    def vet(self, video_id: str) -> dict[str, object]:
        existing = self.store.video(video_id)
        if existing is not None and existing.verdict in {"approved", "rejected", "blocked"}:
            return {
                "verdict": existing.verdict,
                "reasons": existing.verdict_reasons,
                "level": existing.est_level,
                "stage": "cache",
            }
        candidate = self._lookup(video_id)
        if candidate is None:
            return {"verdict": "rejected", "reasons": "unknown video", "level": None, "stage": "hard"}
        verdict = vet_video(
            candidate,
            metadata=cast(MetadataReviewer, self.metadata),
            frames=cast(FrameReviewer, self.frames),
            blocked_channels=self.store.blocked_channels(),
            rejected_ids=self.store.rejected_ids(),
            duration_minutes=self.duration_minutes,
            language=self.language,
        )
        self.store.save_video(
            Video(
                id=candidate.video_id,
                source="youtube",
                source_ref=candidate.video_id,
                title=candidate.title,
                channel_id=candidate.channel_id,
                channel_title=candidate.channel_title,
                duration_s=candidate.duration_s,
                summary=candidate.description[:500],
                verdict=verdict.verdict,
                verdict_reasons=verdict.reasons,
                est_level=verdict.level,
                vetted_at=datetime.now(UTC),
                made_for_kids=1 if candidate.made_for_kids else 0,
                embeddable=1 if candidate.embeddable else 0,
                age_restricted=1 if candidate.age_restricted else 0,
                live=1 if candidate.live else 0,
                short=1 if candidate.short else 0,
                language=candidate.language,
            )
        )
        self._update_reputation(candidate.channel_id, verdict.verdict == "approved")
        return {
            "verdict": verdict.verdict,
            "reasons": verdict.reasons,
            "level": verdict.level,
            "stage": verdict.stage,
        }

    def _remember(self, key: str, candidates: list[VideoCandidate]) -> None:
        index = self.store.get_setting("yt-index", {})
        mapping = dict(index) if isinstance(index, dict) else {}
        for candidate in candidates:
            mapping[candidate.video_id] = candidate_dict(candidate)
        self.store.put_setting("yt-index", mapping, actor="system")
        self.store.put_setting(key, [candidate.video_id for candidate in candidates], actor="system")

    def _load_cached(self, cached_ids: object) -> list[VideoCandidate] | None:
        if not isinstance(cached_ids, list):
            return None
        loaded: list[VideoCandidate] = []
        for video_id in cached_ids:
            candidate = self._lookup(str(video_id))
            if candidate is not None:
                loaded.append(candidate)
        return loaded

    def _lookup(self, video_id: str) -> VideoCandidate | None:
        index = self.store.get_setting("yt-index", {})
        if not isinstance(index, dict):
            return None
        return candidate_from(index.get(video_id))

    def _update_reputation(self, channel_id: str, passed: bool) -> None:
        current = _reputation(self.store.get_setting(f"channel-rep:{channel_id}"))
        updated = update_reputation(current, passed=passed)
        self.store.put_setting(
            f"channel-rep:{channel_id}",
            {
                "passes": updated.passes,
                "failures": updated.failures,
                "preferred": updated.preferred,
                "demoted": updated.demoted,
            },
            actor="system",
        )


def _reputation(value: object) -> ChannelReputation:
    if not isinstance(value, dict):
        return ChannelReputation()
    return ChannelReputation(
        passes=int(str(value.get("passes", 0))),
        failures=int(str(value.get("failures", 0))),
        preferred=bool(value.get("preferred", False)),
        demoted=bool(value.get("demoted", False)),
    )


_ID_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")


def nocookie_embed(video_id: str) -> str:
    if not video_id or any(char not in _ID_CHARS for char in video_id):
        raise ValueError("video id must be a YouTube id")
    return (
        "https://www.youtube-nocookie.com/embed/"
        f"{video_id}?rel=0&controls=0&modestbranding=1&iv_load_policy=3"
    )


def dump_public(payload: dict[str, object]) -> str:
    return json.dumps(payload)
