# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Resolve release track lists, never search-result playlists or narrated videos."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from schoolbookd.content.vetting import VideoCandidate


class AlbumError(ValueError):
    pass


def normalized(value: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold()))


def artists(item: dict[str, Any]) -> list[str]:
    return [str(a.get("name", "")) for a in item.get("artists", []) if isinstance(a, dict)]


def matches(item: dict[str, Any], title: str, artist: str) -> bool:
    return (normalized(str(item.get("title", ""))) == normalized(title)
            and normalized(artist) in [normalized(name) for name in artists(item)])


@dataclass(frozen=True)
class Album:
    album_id: str
    title: str
    artist: str
    tracks: list[VideoCandidate]


class AlbumResolver:
    def __init__(self, videos: Callable[[list[str]], list[VideoCandidate]], music: Any = None) -> None:
        self.videos = videos
        self.music = music

    def resolve(self, title: str, artist: str) -> Album:
        if self.music is not None:
            return self._resolve(self.music, title, artist)
        import requests
        from ytmusicapi import YTMusic

        class BoundedSession(requests.Session):
            def request(self, *args: Any, **kwargs: Any) -> Any:
                kwargs["timeout"] = kwargs.get("timeout") or 10
                return super().request(*args, **kwargs)

        with BoundedSession() as session:
            return self._resolve(YTMusic(requests_session=session), title, artist)

    def _resolve(self, music: Any, title: str, artist: str) -> Album:
        results = music.search(f"{title} {artist}", filter="albums", limit=10)
        exact = [a for a in results if matches(a, title, artist) and a.get("type") == "Album"]
        if not exact:
            raise AlbumError(
                "No exact album and artist match. Ask for the title or artist; do not substitute."
            )
        # Prefer a clean edition when the catalogue lists one with the same title.
        exact.sort(key=lambda a: a.get("isExplicit") is not False)
        selected = exact[0]
        data = music.get_album(selected["browseId"])
        if not matches(data, title, artist) or not str(data.get("audioPlaylistId", "")).startswith("OLAK"):
            raise AlbumError("Could not verify the release identity. Do not play a substitute.")
        tracks = data.get("tracks", [])
        if (not isinstance(tracks, list) or not 1 <= len(tracks) <= 150
                or data.get("trackCount") != len(tracks)):
            raise AlbumError("The album track list is incomplete. Do not play a partial album.")
        ids: list[str] = []
        for track in tracks:
            video_id = str(track.get("videoId") or "")
            if (not re.fullmatch(r"[\w-]{11}", video_id, flags=re.ASCII)
                    or track.get("isAvailable") is not True
                    or normalized(artist) not in [normalized(a) for a in artists(track)]):
                raise AlbumError("An album track is unavailable or has a different artist.")
            ids.append(video_id)
        details = {v.video_id: v for v in self.videos(ids)}
        ordered: list[VideoCandidate] = []
        for track, video_id in zip(tracks, ids, strict=True):
            video = details.get(video_id)
            if video is None or video.age_restricted or video.live or not video.embeddable:
                raise AlbumError("An album track is unavailable for playback.")
            # Release IDs must still belong to that artist, not a reviewer or cover channel.
            channel = re.sub(r"(?:\s*-\s*Topic|VEVO)$", "", video.channel_title, flags=re.I)
            if normalized(channel) != normalized(artist):
                raise AlbumError("Could not verify an album track's artist channel.")
            # Keep the catalogue's track title; API results may carry '(Official Audio)' suffixes.
            ordered.append(replace(video, title=str(track["title"])))
        return Album(str(selected["browseId"]), str(data["title"]), artist, ordered)
