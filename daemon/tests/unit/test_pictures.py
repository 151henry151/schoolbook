# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

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


def test_picture_id_is_a_short_slug() -> None:
    assert picture_id("a dinosaur") == "a-dinosaur"
    assert "/" not in picture_id("T. rex / triceratops")


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
