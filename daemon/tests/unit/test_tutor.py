# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

from schoolbookd.policy.output_check import OutputCheck
from schoolbookd.policy.tools import PolicyContext, ToolPolicy
from schoolbookd.providers.base import FakeLLM, FakeTTS, LLMResponse, SystemBlock, ToolUse
from schoolbookd.tutor.loop import TutorLoop
from schoolbookd.tutor.prompts import AgeProfile, assemble_prompt, render_age_profile
from schoolbookd.tutor.speech import chunk_sentences


def _loop(llm: FakeLLM, clock: list[float] | None = None) -> TutorLoop:
    times = clock or [0.0]

    def now() -> float:
        return times[0]

    return TutorLoop(
        llm=llm,
        policy=ToolPolicy(),
        execute=lambda name, args: {"ok": True, "tool": name, "args": args},
        output_check=OutputCheck([]),
        model="fake",
        clock=now,
    )


def _system() -> list[SystemBlock]:
    return assemble_prompt("core", "age", "learner", "state")


def test_chunker_caps_sentences_and_strips_markdown() -> None:
    text = "Sharks are **old**. They are older than trees. Want to count? One more sentence."
    sentences = chunk_sentences(text, max_sentences=3, max_words=12)
    assert len(sentences) == 3
    assert "**" not in " ".join(sentences)
    long = chunk_sentences(" ".join(["word"] * 30) + ".", max_sentences=3, max_words=12)
    assert all(len(sentence.split()) <= 12 for sentence in long)


def test_fake_tts_silence_grows_with_words() -> None:
    tts = FakeTTS()
    short = tts.synthesize("Hi.")
    longer = tts.synthesize("Hi there friend today")
    assert len(longer) > len(short)
    assert set(short) == {0}


def test_recorded_turn_shows_the_board_then_speaks() -> None:
    llm = FakeLLM(
        [
            LLMResponse(
                text="A volcano is a hot mountain. Want to see one?",
                tool_calls=[
                    ToolUse(
                        "show_board",
                        {"elements": [{"type": "big_text", "text": "volcano"}]},
                    )
                ],
            )
        ]
    )
    outcome = _loop(llm).run_turn(
        "What is a volcano?",
        system=_system(),
        history=[],
        policy_context=PolicyContext(),
    )
    assert outcome.tool_calls[0].allowed
    assert outcome.tool_calls[0].name == "show_board"
    assert "volcano" in " ".join(outcome.sentences).lower()
    assert llm.requests[0].system[0].cache
    assert not llm.requests[0].system[3].cache


def test_unvetted_video_is_not_executed() -> None:
    llm = FakeLLM(
        [
            LLMResponse(
                text="",
                tool_calls=[ToolUse("play_video", {"video_id": "notvetted1"})],
            ),
            LLMResponse(text="That one is not ready. Want a picture instead?"),
        ]
    )
    outcome = _loop(llm).run_turn(
        "Play a video",
        system=_system(),
        history=[],
        policy_context=PolicyContext(),
    )
    assert not outcome.tool_calls[0].allowed
    assert "error" in outcome.tool_calls[0].result
    assert outcome.sentences


def test_empty_transcript_skips_the_model() -> None:
    llm = FakeLLM([])
    outcome = _loop(llm).run_turn(
        "   ",
        system=_system(),
        history=[],
        policy_context=PolicyContext(),
    )
    assert outcome.sentences == ["I didn't catch that."]
    assert llm.requests == []


def test_distress_is_flagged_even_without_a_tool_call() -> None:
    llm = FakeLLM([LLMResponse(text="I am glad you told me. Go find a grown-up now.")])
    outcome = _loop(llm).run_turn(
        "someone is hurting me",
        system=_system(),
        history=[],
        policy_context=PolicyContext(),
    )
    assert outcome.flagged
    assert "grown-up" in " ".join(outcome.sentences)


def test_output_check_replaces_the_turn(tmp_path: Path) -> None:
    path = tmp_path / "words.txt"
    path.write_text("password\n", encoding="utf-8")
    llm = FakeLLM([LLMResponse(text="Please say your password now.")])
    loop = _loop(llm)
    loop.output_check = OutputCheck.load(path)
    outcome = loop.run_turn(
        "hello",
        system=_system(),
        history=[],
        policy_context=PolicyContext(),
    )
    assert outcome.redirected
    assert "password" not in outcome.sentences[0]


def test_wall_clock_forces_speech() -> None:
    llm = FakeLLM([LLMResponse(text="Too late.")])
    ticks = iter([0.0, 30.0])

    def now() -> float:
        return next(ticks)

    outcome = TutorLoop(
        llm=llm,
        policy=ToolPolicy(),
        execute=lambda name, args: {"ok": True},
        output_check=OutputCheck([]),
        model="fake",
        clock=now,
    ).run_turn("hi", system=_system(), history=[], policy_context=PolicyContext())
    assert llm.requests == []
    assert outcome.sentences


def test_long_history_is_folded() -> None:
    llm = FakeLLM([LLMResponse(text="Still here.")])
    history = [{"role": "user", "content": f"turn {index}"} for index in range(20)]
    loop = _loop(llm)
    loop.history_limit = 4
    loop.run_turn("now", system=_system(), history=history, policy_context=PolicyContext())
    messages = llm.requests[0].messages
    assert len(messages) < 20
    assert str(messages[0]["content"]).startswith("Earlier:")


def test_age_profile_text_mentions_the_sentence_cap() -> None:
    text = render_age_profile(AgeProfile(id="age-6", max_sentences_per_turn=3))
    assert "3 sentences" in text
