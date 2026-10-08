# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""YouTube Data API search. Results are filtered before the tutor sees them."""

from __future__ import annotations

import httpx

from schoolbookd.content.vetting import VideoCandidate


class YouTubeClient:
    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(base_url="https://www.googleapis.com", timeout=20)

    def search(self, query: str) -> list[VideoCandidate]:
        response = self._client.get(
            "/youtube/v3/search",
            params={
                "part": "snippet",
                "type": "video",
                "safeSearch": "strict",
                "videoEmbeddable": "true",
                "videoDuration": "medium",
                "q": query,
                "key": self._api_key,
                "maxResults": 8,
            },
        )
        response.raise_for_status()
        ids = [
            item["id"]["videoId"]
            for item in response.json().get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        if not ids:
            return []
        details = self._client.get(
            "/youtube/v3/videos",
            params={"part": "snippet,contentDetails,status", "id": ",".join(ids), "key": self._api_key},
        )
        details.raise_for_status()
        return [_candidate(item) for item in details.json().get("items", [])]


def _candidate(item: dict[str, object]) -> VideoCandidate:
    snippet = item.get("snippet")
    status = item.get("status")
    details = item.get("contentDetails")
    if not isinstance(snippet, dict) or not isinstance(status, dict) or not isinstance(details, dict):
        raise ValueError("unexpected YouTube payload")
    duration = _iso_duration(str(details.get("duration", "PT0S")))
    return VideoCandidate(
        video_id=str(item.get("id", "")),
        title=str(snippet.get("title", "")),
        channel_id=str(snippet.get("channelId", "")),
        channel_title=str(snippet.get("channelTitle", "")),
        description=str(snippet.get("description", "")),
        duration_s=duration,
        embeddable=bool(status.get("embeddable", False)),
        age_restricted=snippet.get("contentRating") not in (None, {}),
        live=snippet.get("liveBroadcastContent") == "live",
        short=duration < 60,
        language=str(snippet.get("defaultAudioLanguage", "en"))[:2],
        made_for_kids=bool(status.get("madeForKids", False)),
    )


def _iso_duration(value: str) -> int:
    digits = ""
    total = 0
    units = {"H": 3600, "M": 60, "S": 1}
    for char in value:
        if char.isdigit():
            digits += char
        elif char in units and digits:
            total += int(digits) * units[char]
            digits = ""
    return total
