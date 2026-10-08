# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

import httpx

from schoolbookd.content.pictures import TINY_PNG, FakePictures, picture_id, picture_prompt
from schoolbookd.db.engine import make_engine, migrate, session_factory
from schoolbookd.db.store import Store
from schoolbookd.policy.output_check import OutputCheck
from schoolbookd.providers.base import FakeLLM, FakeTTS
from schoolbookd.runtime import LiveState, Runtime
from schoolbookd.tutor.prompts import AgeProfile


def _store(tmp_path: Path) -> Store:
    engine = make_engine(tmp_path / "schoolbook.db")
    migrate(engine)
    store = Store(session_factory(engine))
    store.upsert_learner(learner_id="kid", first_name="Arum", birth_year=2020)
    return store


def test_picture_prompt_asks_for_a_clear_educational_drawing() -> None:
    text = picture_prompt("dinosaur")
    lowered = text.lower()
    assert "dinosaur" in lowered
    assert "text" in lowered or "letters" in lowered
    assert "six" in lowered or "child" in lowered
    compare = picture_prompt("great white shark dive next to stacked houses")
    assert "compar" in compare.lower()


def test_picture_prompt_uses_the_tutor_brief_for_a_scale_diagram() -> None:
    brief = (
        "Generate an image of a great white shark using a house for scale. "
        "Show how many houses stacked on top of each other would show how deep "
        "a great white shark dives."
    )
    text = picture_prompt(brief)
    lowered = text.lower()
    assert "stacked" in lowered
    assert "house" in lowered
    assert "svg" in lowered
    assert "artistic" in lowered or "scene" in lowered
    assert "illustrat" in lowered or "point" in lowered
    assert "judgment" in lowered or "choose" in lowered or "best way" in lowered
    assert "ruler" in lowered or "tick" in lowered


def test_picture_prompt_leaves_room_for_non_size_questions() -> None:
    brief = "Show how a volcano works: magma, the cone, and ash coming out the top."
    text = picture_prompt(brief)
    lowered = text.lower()
    assert "volcano" in lowered
    assert "magma" in lowered
    assert "judgment" in lowered or "choose" in lowered or "best way" in lowered
    assert "stacked houses" not in lowered


def test_picture_id_is_a_short_slug() -> None:
    assert picture_id("a dinosaur") == "a-dinosaur"
    assert "/" not in picture_id("T. rex / triceratops")


def test_picture_id_changes_when_the_brief_changes() -> None:
    first = picture_id("shark depth", "stack houses to show dive depth")
    second = picture_id("shark depth", "compare length to a bus")
    assert first != second
    assert picture_id("dinosaur") == "dinosaur"


def test_show_picture_saves_a_local_image(tmp_path: Path) -> None:
    store = _store(tmp_path)
    images = tmp_path / "images"
    runtime = Runtime(
        store=store,
        llm=FakeLLM([]),
        tts=FakeTTS(),
        output_check=OutputCheck([]),
        apps={},
        age_profile=AgeProfile(id="age-6"),
        core_prompt="computer helper",
        pictures=FakePictures(),
        images_dir=images,
    )
    live = LiveState(session_id=store.start_session("kid", "fake"), learner_id="kid")
    result = runtime.run_tool(live, "show_picture", {"topic": "dinosaur"})
    assert result["shown"] is True
    assert result["image_id"] == "dinosaur"
    path = runtime.image_path("dinosaur")
    assert path is not None
    assert path.read_bytes() == TINY_PNG
    assert "dinosaur" in store.image_ids()
    again = runtime.run_tool(live, "show_picture", {"topic": "dinosaur"})
    assert again["image_id"] == "dinosaur"


def test_deferred_show_picture_returns_loading_then_saves(tmp_path: Path) -> None:
    store = _store(tmp_path)
    images = tmp_path / "images"
    runtime = Runtime(
        store=store,
        llm=FakeLLM([]),
        tts=FakeTTS(),
        output_check=OutputCheck([]),
        apps={},
        age_profile=AgeProfile(id="age-6"),
        core_prompt="computer helper",
        pictures=FakePictures(),
        images_dir=images,
    )
    live = LiveState(session_id=store.start_session("kid", "fake"), learner_id="kid")
    started = runtime.run_tool(live, "show_picture", {"topic": "shark depth"}, defer_pictures=True)
    assert started.get("loading") is True
    assert started["image_id"] == "shark-depth"
    assert runtime.image_path("shark-depth") is None
    finished = runtime.finish_picture(live, "shark depth", "shark-depth")
    assert finished["shown"] is True
    path = runtime.image_path("shark-depth")
    assert path is not None
    assert path.read_bytes() == TINY_PNG


def test_show_picture_sends_the_tutor_brief_to_the_picture_maker(tmp_path: Path) -> None:
    store = _store(tmp_path)
    images = tmp_path / "images"
    pictures = FakePictures()
    runtime = Runtime(
        store=store,
        llm=FakeLLM([]),
        tts=FakeTTS(),
        output_check=OutputCheck([]),
        apps={},
        age_profile=AgeProfile(id="age-6"),
        core_prompt="computer helper",
        pictures=pictures,
        images_dir=images,
    )
    live = LiveState(session_id=store.start_session("kid", "fake"), learner_id="kid")
    brief = (
        "Draw a great white shark beside a stack of houses that shows how deep it dives."
    )
    result = runtime.run_tool(live, "show_picture", {"topic": "shark depth", "brief": brief})
    assert result["shown"] is True
    assert pictures.prompts
    sent = pictures.prompts[-1].lower()
    assert "stack of houses" in sent
    assert "svg" in sent


def test_extract_svg_takes_the_diagram_from_claude_text() -> None:
    from schoolbookd.providers.claude_pictures import extract_svg

    svg = extract_svg('Here you go:\n<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>\n')
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")


def test_claude_draws_an_svg_diagram_from_the_brief() -> None:
    from schoolbookd.providers.claude_pictures import ClaudePictures

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": '<svg xmlns="http://www.w3.org/2000/svg"><circle r="4"/></svg>',
                    }
                ]
            },
        )

    maker = ClaudePictures(
        "key",
        model="claude-sonnet-5-5",
        client=httpx.Client(base_url="https://api.anthropic.com", transport=httpx.MockTransport(handler)),
    )
    data = maker.generate(picture_prompt("stack houses to show shark depth"))
    assert data.startswith(b"<svg")
    body = str(captured["body"]).lower()
    assert "svg" in body
    assert "shark" in body or "house" in body
    assert "judgment" in body or "choose" in body or "illustrat" in body
