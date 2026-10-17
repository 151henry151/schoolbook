# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Search cache, vetting, and channel reputation. The tutor never receives a URL."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol, cast

from schoolbookd.content.albums import AlbumError, AlbumResolver
from schoolbookd.content.vetting import (
    ChannelReputation,
    FrameReviewer,
    MetadataReviewer,
    Review,
    VideoCandidate,
    educational_search_query,
    hard_filter,
    preschool_search_query,
    rank_for_clean_audio,
    rank_for_preschool,
    rank_for_stretch,
    song_search_query,
    update_reputation,
    vet_video,
    visible_to_tutor,
)
from schoolbookd.db.models import Video
from schoolbookd.db.store import Store
from schoolbookd.tutor.prompts import AgeProfile


class SearchClient(Protocol):
    def search(self, query: str, **kwargs: object) -> list[VideoCandidate]: ...


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


_QUERY_STOP = {
    "about",
    "educational",
    "explainer",
    "documentary",
    "kids",
    "video",
    "videos",
    "show",
    "some",
    "facts",
    "lesson",
}


def candidate_from_row(video: Video) -> VideoCandidate:
    return VideoCandidate(
        video_id=video.id,
        title=video.title,
        channel_id=video.channel_id,
        channel_title=video.channel_title,
        description=video.summary,
        duration_s=video.duration_s,
        embeddable=bool(video.embeddable),
        age_restricted=bool(video.age_restricted),
        live=bool(video.live),
        short=bool(video.short),
        language=video.language or "en",
        made_for_kids=bool(video.made_for_kids),
    )


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
        albums: AlbumResolver | None = None,
        preschool: bool = False,
    ) -> None:
        self.store = store
        self.youtube = youtube
        self.metadata = metadata
        self.frames = frames
        self.duration_minutes = duration_minutes
        self.language = language
        self.albums = albums
        self.preschool = preschool

    def for_profile(self, profile: AgeProfile) -> VideoCatalog:
        window = (profile.video_duration_minutes[0], profile.video_duration_minutes[1])
        return VideoCatalog(self.store, self.youtube, self.metadata, self.frames,
                            duration_minutes=window, language=profile.language,
                            albums=self.albums, preschool=profile.age_years <= 4)

    def playable(self, video_id: str) -> bool:
        row = self.store.video(video_id)
        return bool(row and self._filter([candidate_from_row(row)]))

    def _filter(self, videos: list[VideoCandidate], *, kind: str = "video") -> list[VideoCandidate]:
        return visible_to_tutor(videos, blocked_channels=self.store.blocked_channels(),
                                rejected_ids=self.store.rejected_ids(), duration_minutes=self.duration_minutes,
                                language=self.language, kind=kind,
                                preschool=self.preschool)

    def _rank(self, videos: list[VideoCandidate]) -> list[VideoCandidate]:
        return rank_for_preschool(videos) if self.preschool else rank_for_stretch(videos)

    def find_album(self, title: str, artist: str) -> dict[str, object]:
        if self.albums is None:
            return {"error": "Album lookup is unavailable. Do not substitute videos or songs."}
        try:
            album = self.albums.resolve(title, artist)
            blocked = self.store.blocked_channels()
            rejected = self.store.rejected_ids()
            if any(v.channel_id in blocked or v.video_id in rejected for v in album.tracks):
                raise AlbumError("An album track is blocked. Cannot play the complete album.")
            self._approve_requested_songs(album.tracks)
            result: dict[str, object] = {
                "album_id": album.album_id, "title": album.title, "artist": album.artist,
                "tracks": [{"video_id": v.video_id, "title": v.title} for v in album.tracks],
            }
            self.store.put_setting("verified-album:" + album.album_id, result, actor="system")
            return result
        except AlbumError as exc:
            return {"error": str(exc)}
        except Exception:
            return {"error": "Album service unavailable. Try again later; do not play a substitute."}

    def album_tracks(self, album_id: str) -> list[str]:
        album = self.store.get_setting("verified-album:" + album_id)
        if not isinstance(album, dict) or not isinstance(album.get("tracks"), list):
            return []
        return [str(track["video_id"]) for track in album["tracks"]]

    def search(self, query: str, *, kind: str = "video") -> list[dict[str, object]]:
        song = kind == "song"
        shape_video = preschool_search_query if self.preschool else educational_search_query
        shaped = song_search_query(query) if song else shape_video(query)
        prefix = "yt-song-v1:" if song else "yt-preschool-v1:" if self.preschool else "yt-cache-v2:"
        key = prefix + shaped.strip().lower()
        cached_ids = self.store.get_setting(key)
        candidates = self._load_cached(cached_ids)
        if candidates is None:
            if self.youtube is not None:
                candidates = self.youtube.search(shaped, music=song)
            else:
                candidates = []
            if candidates:
                self._remember(key, candidates)
        visible = self._filter(candidates, kind="song" if song else "video")
        kept = rank_for_clean_audio(visible) if song else self._rank(visible)
        if song:
            self._approve_requested_songs(kept)
        elif not kept:
            kept = self._approved_matching(query)
        return [public_candidate(video) for video in kept]

    def _approve_requested_songs(self, videos: list[VideoCandidate]) -> None:
        for video in videos:
            existing = self.store.video(video.video_id)
            if existing is not None and existing.verdict == "blocked":
                continue
            self.store.save_video(
                Video(
                    id=video.video_id,
                    source="youtube",
                    source_ref=video.video_id,
                    title=video.title,
                    channel_id=video.channel_id,
                    channel_title=video.channel_title,
                    duration_s=video.duration_s,
                    summary=video.description[:500],
                    verdict="approved",
                    verdict_reasons="requested song audio",
                    est_level=1,
                    vetted_at=datetime.now(UTC),
                    made_for_kids=1 if video.made_for_kids else 0,
                    embeddable=1 if video.embeddable else 0,
                    age_restricted=1 if video.age_restricted else 0,
                    live=1 if video.live else 0,
                    short=1 if video.short else 0,
                    language=video.language,
                )
            )

    def vet(self, video_id: str) -> dict[str, object]:
        existing = self.store.video(video_id)
        candidate = self._lookup(video_id) or (candidate_from_row(existing) if existing else None)
        if candidate is not None:
            hard = hard_filter(candidate, blocked_channels=self.store.blocked_channels(),
                               rejected_ids=set(), duration_minutes=self.duration_minutes,
                               language=self.language, preschool=self.preschool)
            if not hard.ok:
                return {"verdict": "rejected", "reasons": hard.reason, "level": None, "stage": "hard"}
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
            preschool=self.preschool,
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

    def _approved_matching(self, query: str) -> list[VideoCandidate]:
        words = [
            word
            for word in re.findall(r"[a-z0-9]+", query.lower())
            if len(word) > 3 and word not in _QUERY_STOP
        ]
        if not words:
            return []
        matches: list[VideoCandidate] = []
        for video in self.store.approved_videos():
            text = f"{video.title} {video.summary}".lower()
            if any(word in text for word in words):
                matches.append(self._lookup(video.id) or candidate_from_row(video))
        return self._rank(self._filter(matches))

    def _load_cached(self, cached_ids: object) -> list[VideoCandidate] | None:
        if not isinstance(cached_ids, list) or not cached_ids:
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
        f"{video_id}?rel=0&controls=0&modestbranding=1&iv_load_policy=3&autoplay=1"
    )


def dump_public(payload: dict[str, object]) -> str:
    return json.dumps(payload)
