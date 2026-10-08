# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

import httpx

from schoolbookd.evals.kid_speak import passes, suite_pass_rate
from schoolbookd.providers.anthropic import AnthropicLLM
from schoolbookd.providers.base import LLMRequest, SystemBlock
from schoolbookd.providers.piper import piper_command
from schoolbookd.providers.whisper import whisper_command
from schoolbookd.providers.youtube import YouTubeClient, _iso_duration


def test_iso_duration() -> None:
    assert _iso_duration("PT5M3S") == 303
    assert _iso_duration("PT45S") == 45


def test_youtube_search_uses_safe_search() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({key: request.url.params[key] for key in request.url.params})
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"items": [{"id": {"videoId": "abcdefghijk"}}]})
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "abcdefghijk",
                        "snippet": {
                            "title": "Volcanoes",
                            "channelId": "chan",
                            "channelTitle": "Kids",
                            "description": "Rocks",
                            "defaultAudioLanguage": "en",
                        },
                        "status": {"embeddable": True, "madeForKids": True},
                        "contentDetails": {"duration": "PT5M"},
                    }
                ]
            },
        )

    client = YouTubeClient(
        "key",
        httpx.Client(base_url="https://www.googleapis.com", transport=httpx.MockTransport(handler)),
    )
    videos = client.search("volcanoes for kids")
    assert videos[0].title == "Volcanoes"
    assert seen[0]["safeSearch"] == "strict"
    assert seen[0]["videoEmbeddable"] == "true"
    assert seen[0]["videoDuration"] == "medium"


def test_anthropic_marks_only_cacheable_blocks() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
            import json

            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"content": [{"type": "text", "text": "Hi."}]})

    llm = AnthropicLLM(
        "key",
        "claude-haiku-5-5",
        httpx.Client(base_url="https://api.anthropic.com", transport=httpx.MockTransport(handler)),
    )
    result = llm.complete(
        LLMRequest(
            model="claude-haiku-5-5",
            system=[
                SystemBlock("core", True),
                SystemBlock("age", True),
                SystemBlock("learner", True),
                SystemBlock("now", False),
            ],
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    body = captured["body"]
    assert isinstance(body, dict)
    system = body["system"]
    assert isinstance(system, list)
    assert "cache_control" in system[0]
    assert "cache_control" not in system[-1]
    assert result.text == "Hi."


def test_local_provider_commands() -> None:
    assert piper_command("hi", Path("voice.onnx"))[0] == "piper"
    assert whisper_command(Path("in.wav"), Path("model.bin"))[0] == "whisper-cli"


def test_kid_speak_suite_meets_the_threshold() -> None:
    replies = ["Sharks are old. Want to count teeth?"] * 100
    replies.append("This reply is **markdown** and it goes on and on with too many words " * 5)
    assert passes("Sharks are old. Want to count teeth?")
    assert not passes("Hello **friend**.")
    assert suite_pass_rate(replies[:100]) >= 0.95
