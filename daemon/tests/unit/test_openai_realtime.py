# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

import asyncio
import json

from schoolbookd.providers.openai_realtime import (
    REALTIME_TOOLS,
    RealtimeMapper,
    RealtimeTalk,
    answer_first_nudge,
    child_speech_decision,
    clarify_speech_note,
    connect_headers,
    extract_child_speech,
    game_play_briefing,
    game_topic,
    looks_like_child_speech,
    looks_like_curious_question,
    looks_like_fantasy,
    maybe_song_topic,
    paused_video_note,
    picture_making_line,
    picture_wait_instructions,
    real_world_nudge,
    resample_pcm16,
    session_update,
    song_confirm_briefing,
    song_listen_briefing,
    song_topic,
    spoken_child_instructions,
    spoken_clarify,
    video_watch_briefing,
)


def test_session_update_disables_barge_in_and_uses_server_vad() -> None:
    payload = session_update(instructions="Be a computer helper.", tools=[{"name": "show_board"}])
    session = payload["session"]
    assert payload["type"] == "session.update"
    assert session["instructions"] == "Be a computer helper."
    turn = session["audio"]["input"]["turn_detection"]
    assert turn["type"] == "server_vad"
    assert turn["interrupt_response"] is False
    assert turn["create_response"] is False
    assert int(turn["silence_duration_ms"]) >= 1500
    assert float(turn["threshold"]) >= 0.55
    assert session["tools"][0]["name"] == "show_board"
    assert session["audio"]["output"]["voice"] == "marin"
    assert float(session["audio"]["output"]["speed"]) <= 0.9
    cedar = session_update(instructions="Be a computer helper.", tools=[], voice="cedar")
    assert cedar["session"]["audio"]["output"]["voice"] == "cedar"


def test_audio_delta_becomes_a_child_audio_chunk() -> None:
    mapper = RealtimeMapper(turn_id="live")
    ui, outbound = mapper.handle({"type": "response.output_audio.delta", "delta": "AQID"})
    assert outbound == []
    assert ui[0]["type"] == "audio_chunk"
    assert ui[0]["pcm_b64"] == "AQID"
    assert ui[0]["sample_rate"] == 24000
    assert ui[0]["turn_id"] == "live"


def test_legacy_audio_delta_name_is_accepted() -> None:
    mapper = RealtimeMapper()
    ui, _outbound = mapper.handle({"type": "response.audio.delta", "delta": "AA=="})
    assert ui[0]["type"] == "audio_chunk"


def test_speech_and_response_events_drive_ui_state() -> None:
    mapper = RealtimeMapper()
    started, _ = mapper.handle({"type": "input_audio_buffer.speech_started"})
    assert started[0] == {"type": "state", "name": "listening", "detail": "hearing"}
    stopped, _ = mapper.handle({"type": "input_audio_buffer.speech_stopped"})
    assert stopped[0]["name"] == "thinking"
    done, _ = mapper.handle({"type": "response.done"})
    assert done[0] == {"type": "state", "name": "listening", "detail": ""}


def test_function_call_runs_the_schoolbook_tool() -> None:
    seen: list[tuple[str, dict[str, object]]] = []

    def execute(name: str, args: dict[str, object]) -> dict[str, object]:
        seen.append((name, args))
        return {"shown": True}

    mapper = RealtimeMapper()
    ui, outbound = mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "c1",
            "name": "show_board",
            "arguments": '{"elements":[{"type":"big_text","text":"hi","highlights":[]}]}',
        },
        execute=execute,
    )
    assert seen[0][0] == "show_board"
    assert ui[0]["type"] == "board"
    assert outbound[0]["type"] == "conversation.item.create"
    assert outbound[0]["item"]["call_id"] == "c1"
    assert outbound[1]["type"] == "response.create"


def test_child_transcript_waits_until_the_agent_heard_the_sentence() -> None:
    mapper = RealtimeMapper()
    first, outbound = mapper.handle(
        {"type": "conversation.item.input_audio_transcription.delta", "delta": "The deep"}
    )
    second, _ = mapper.handle(
        {"type": "conversation.item.input_audio_transcription.delta", "delta": " of the"}
    )
    assert first == []
    assert second == []
    assert outbound == []
    done, reply = mapper.handle(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "How deep can a great white shark go?",
        }
    )
    assert done[0]["role"] == "child"
    assert done[0]["text"] == "How deep can a great white shark go?"
    assert done[0]["partial"] is False
    assert reply[-1]["type"] == "response.create"


def test_tutor_transcript_deltas_stream_while_speaking() -> None:
    mapper = RealtimeMapper()
    first, _ = mapper.handle({"type": "response.output_audio_transcript.delta", "delta": "I will "})
    second, _ = mapper.handle({"type": "response.audio_transcript.delta", "delta": "put it on."})
    assert first[0]["role"] == "tutor"
    assert first[0]["text"] == "I will "
    assert first[0]["partial"] is True
    assert second[0]["text"] == "I will put it on."


def test_child_transcript_is_forwarded() -> None:
    mapper = RealtimeMapper()
    ui, outbound = mapper.handle(
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": "hello"}
    )
    assert ui[0]["type"] == "transcript"
    assert ui[0]["role"] == "child"
    assert ui[0]["text"] == "hello"
    assert outbound[-1]["type"] == "response.create"
    assert all(item.get("type") != "conversation.item.create" for item in outbound)


def test_video_watch_briefing_asks_for_history_or_science() -> None:
    text = video_watch_briefing("Show me some dinosaur videos", name="Arum")
    assert text is not None
    lowered = text.lower()
    assert "six-year-old" in lowered
    assert "arum" in lowered
    assert "dinosaur" in lowered
    assert "educational" in lowered
    assert "history" in lowered
    assert "science" in lowered
    assert "youtube" in lowered
    assert video_watch_briefing("I like cookies") is None
    assert video_watch_briefing("Can I learn about how deep a great white shark has to go?") is None
    assert video_watch_briefing("How deep do sharks go?") is None
    assert video_watch_briefing("I want to hear Astronaut in the Ocean") is None


def test_a_song_request_asks_for_clean_audio_only() -> None:
    asked = "I want to hear Astronaut in the Ocean"
    assert song_topic(asked) == "Astronaut in the Ocean"
    assert song_topic("Play Astronaut in the Ocean") == "Astronaut in the Ocean"
    assert song_topic("Play the song Baby Shark") == "Baby Shark"
    assert song_topic("I want to hear about sharks") is None
    assert song_topic("How deep do sharks go?") is None
    assert song_topic("It can hear you. Do you sound a girl now or a boy?") is None
    assert song_topic("Can you hear me?") is None
    assert song_topic("I want to play a game") is None
    assert song_topic("Play a game") is None
    assert song_topic("Can I play GCompris") is None
    assert song_topic("Play with me") is None
    assert song_topic("I want to play") is None
    assert song_topic("Play Happy") is None
    assert maybe_song_topic("Play Happy") == "Happy"
    assert maybe_song_topic("Play a game") is None
    assert maybe_song_topic("I want to play a game") is None
    assert maybe_song_topic("Play Astronaut in the Ocean") is None
    note = song_listen_briefing(asked, name="Arum")
    assert note is not None
    lowered = note.lower()
    assert "arum" in lowered
    assert "astronaut in the ocean" in lowered
    assert "okay, i'll play" in lowered
    assert "do not say clean" in lowered or "do not say" in lowered and "clean" in lowered
    assert "audio_only" in lowered or "audio only" in lowered
    mapper = RealtimeMapper(child_name="Arum")
    _ui, outbound = mapper.handle(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": asked,
        }
    )
    notes = [
        str(item["item"]["content"][0]["text"])
        for item in outbound
        if item.get("type") == "conversation.item.create"
    ]
    assert any("clean" in note.lower() and "audio" in note.lower() for note in notes)
    assert song_listen_briefing("I want to play a game", name="Arum") is None
    confirm = song_confirm_briefing("Play Happy", name="Arum")
    assert confirm is not None
    assert "did you mean you wanted to hear the song called happy" in confirm.lower()
    assert "wait" in confirm.lower()
    assert song_confirm_briefing(asked, name="Arum") is None


def test_a_game_request_does_not_look_up_a_song() -> None:
    mapper = RealtimeMapper(child_name="Arum")
    _ui, outbound = mapper.handle(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "I want to play a game.",
        }
    )
    notes = [
        str(item["item"]["content"][0]["text"])
        for item in outbound
        if item.get("type") == "conversation.item.create"
    ]
    joined = " ".join(notes).lower()
    assert "okay, i'll play" not in joined
    assert "kind song" not in joined
    assert "search_videos" not in joined
    assert game_topic("I want to play a game") == "any"
    assert game_topic("I want to play a counting game") == "counting"
    assert game_topic("Play a memory game") == "memory"
    assert game_topic("Play Astronaut in the Ocean") is None
    assert game_topic("Play Happy") is None
    ask = game_play_briefing("I want to play a game", name="Arum")
    assert ask is not None
    assert "what kind" in ask.lower()
    assert "gcompris" in ask.lower()
    assert "wait" in ask.lower()
    pick = game_play_briefing("I want to play a counting game", name="Arum")
    assert pick is not None
    assert "counting" in pick.lower()
    assert "launch_app" in pick
    assert any("gcompris" in note.lower() and "what kind" in note.lower() for note in notes)


def test_an_ambiguous_play_asks_if_it_is_a_song() -> None:
    mapper = RealtimeMapper(child_name="Arum")
    _ui, outbound = mapper.handle(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "Play Happy.",
        }
    )
    notes = [
        str(item["item"]["content"][0]["text"])
        for item in outbound
        if item.get("type") == "conversation.item.create"
    ]
    assert any("did you mean you wanted to hear the song called happy" in note.lower() for note in notes)
    assert all("okay, i'll play" not in note.lower() for note in notes)


def test_video_request_sends_an_educational_briefing_to_the_model() -> None:
    mapper = RealtimeMapper(child_name="Arum")
    ui, outbound = mapper.handle(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "Show me some dinosaur videos.",
        }
    )
    assert ui[0]["text"] == "Show me some dinosaur videos."
    assert outbound[0]["type"] == "conversation.item.create"
    briefing = str(outbound[0]["item"]["content"][0]["text"])
    assert "six-year-old" in briefing.lower()
    assert "dinosaur" in briefing.lower()
    assert "educational" in briefing.lower()
    assert outbound[-1]["type"] == "response.create"


def test_connect_headers_use_the_ga_realtime_api() -> None:
    headers = connect_headers("sk-test")
    assert headers["Authorization"] == "Bearer sk-test"
    assert "OpenAI-Beta" not in headers


def test_error_event_stays_on_realtime_voice() -> None:
    mapper = RealtimeMapper()
    ui, _ = mapper.handle({"type": "error", "error": {"message": "nope"}})
    assert ui[0] == {"type": "state", "name": "listening", "detail": ""}
    assert "pipeline" not in json.dumps(ui)


def test_realtime_tools_do_not_offer_written_menus() -> None:
    names = [str(tool.get("name")) for tool in REALTIME_TOOLS]
    assert "ask_choice" not in names
    assert "show_board" in names
    assert "search_videos" in names
    assert "vet_video" in names
    assert "play_video" in names
    search = next(tool for tool in REALTIME_TOOLS if tool.get("name") == "search_videos")
    assert "kind" in search["parameters"]["properties"]
    play = next(tool for tool in REALTIME_TOOLS if tool.get("name") == "play_video")
    assert "audio_only" in play["parameters"]["properties"]
    assert "video_control" in names
    assert "show_picture" in names
    assert "switch_voice" not in names
    assert "set_tutor_name" in names
    assert "list_apps" in names
    assert "launch_app" in names
    picture = next(tool for tool in REALTIME_TOOLS if tool.get("name") == "show_picture")
    props = picture["parameters"]["properties"]
    assert "brief" in props
    assert "topic" in props
    desc = str(picture.get("description", "")).lower()
    assert "illustrat" in desc or "point" in desc
    assert "claude" in desc or "choose" in desc or "judgment" in desc


def test_spoken_instructions_tell_the_tutor_to_find_videos_itself() -> None:
    text = spoken_child_instructions("charter", "age-6", "Arum")
    lowered = text.lower()
    assert "search_videos" in text
    assert "vet_video" in text
    assert "play_video" in text
    assert "video id" in lowered or "video_id" in lowered
    assert "never ask" in lowered
    assert "show_picture" in text
    assert "brief" in lowered
    assert "claude" in lowered
    assert "illustrat" in lowered or "point" in lowered or "judgment" in lowered
    assert "made-up" in lowered or "story" in lowered or "pretend" in lowered
    assert "real" in lowered
    assert "answer" in lowered
    assert "default" in lowered
    assert "words" in lowered or "verbally" in lowered or "talk" in lowered
    assert "consider" in lowered
    assert "very helpful" in lowered
    assert "suggest" in lowered
    assert "song" in lowered or "hear" in lowered
    assert "i'll play" in lowered or "okay, i'll play" in lowered
    assert "did you mean you wanted to hear the song called" in lowered
    assert "game" in lowered
    assert "gcompris" in lowered
    assert "list_apps" in text
    assert "launch_app" in text
    assert "do not say clean" in lowered or "don't say clean" in lowered
    assert "finish" in lowered or "this turn" in lowered or "lead-in" in lowered
    assert "switch_voice" not in text
    assert "i'm sorry, no, i can't, this is my voice" in lowered


def test_a_curious_question_gets_an_answer_and_picture_not_a_video() -> None:
    asked = "Can I learn about how deep a great white shark has to go?"
    assert looks_like_curious_question(asked)
    assert looks_like_curious_question("How deep do sharks go?")
    assert looks_like_curious_question("Why is the sky blue?")
    assert not looks_like_curious_question("Hello how are you doing?")
    assert not looks_like_curious_question("Show me some dinosaur videos")
    note = answer_first_nudge(asked, name="Arum")
    assert note is not None
    lowered = note.lower()
    assert "arum" in lowered
    assert "picture" in lowered
    assert "default" in lowered
    assert "words" in lowered or "verbally" in lowered or "talk" in lowered
    assert "consider" in lowered
    assert "very helpful" in lowered
    assert "suggest" in lowered
    assert "this turn" in lowered or "lead-in" in lowered or "do not stop" in lowered
    assert answer_first_nudge("Show me some shark videos") is None
    assert answer_first_nudge("Tell me about Elsa") is None
    mapper = RealtimeMapper(child_name="Arum")
    _ui, outbound = mapper.handle(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": asked,
        }
    )
    notes = [
        str(item["item"]["content"][0]["text"])
        for item in outbound
        if item.get("type") == "conversation.item.create"
    ]
    assert any("default" in note.lower() and "consider" in note.lower() for note in notes)
    assert any("very helpful" in note.lower() for note in notes)
    assert any("suggest" in note.lower() and "video" in note.lower() for note in notes)
    create = next(item for item in outbound if item.get("type") == "response.create")
    create_text = str(create.get("response", {}).get("instructions", "")).lower()
    assert "answer" in create_text
    assert "words" in create_text or "default" in create_text
    assert "lead-in" in create_text or "do not stop" in create_text or "this turn" in create_text


def test_fantasy_talk_gets_a_gentle_nudge_toward_real_things() -> None:
    assert looks_like_fantasy("Tell me about Elsa from Frozen")
    assert looks_like_fantasy("Show me a Pokemon video")
    assert not looks_like_fantasy("How do airplanes fly?")
    assert not looks_like_fantasy("What does a komodo dragon eat?")
    note = real_world_nudge("Tell me about Elsa", name="Arum")
    assert note is not None
    lowered = note.lower()
    assert "arum" in lowered
    assert "real" in lowered
    assert real_world_nudge("How do airplanes fly?") is None
    mapper = RealtimeMapper(child_name="Arum")
    _ui, outbound = mapper.handle(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "Tell me about Elsa.",
        }
    )
    briefing = str(outbound[0]["item"]["content"][0]["text"])
    assert "real" in briefing.lower()
    assert outbound[-1]["type"] == "response.create"


def test_looks_like_child_speech_rejects_garbled_words() -> None:
    assert looks_like_child_speech("How big is a blue whale next to a school bus?")
    assert looks_like_child_speech("Show me a dinosaur.")
    assert looks_like_child_speech("yes")
    assert looks_like_child_speech("T rex")
    assert not looks_like_child_speech("")
    assert not looks_like_child_speech("...")
    assert not looks_like_child_speech("asdfkj mmm fff")
    assert not looks_like_child_speech("blargh zzzz qkpt")


def test_extract_child_speech_drops_fillers_and_keeps_the_sentence() -> None:
    assert extract_child_speech("Um, how big is a blue whale?").lower() == "how big is a blue whale?"
    assert extract_child_speech("uh uh yes") == "yes"
    assert child_speech_decision("um") == ("wait", "")
    assert child_speech_decision("Uh") == ("wait", "")
    assert child_speech_decision("Ča") == ("wait", "")
    assert child_speech_decision("人不气") == ("wait", "")
    assert child_speech_decision("Um, show me a dinosaur.") == ("ready", "show me a dinosaur.")
    assert child_speech_decision("asdfkj") == ("wait", "")
    assert child_speech_decision("asdfkj mmm fff")[0] == "unclear"


def test_filler_only_transcript_keeps_listening() -> None:
    mapper = RealtimeMapper()
    ui, outbound = mapper.handle(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "Um",
        }
    )
    assert ui == []
    assert outbound == []


def test_unclear_transcript_asks_the_child_to_confirm() -> None:
    said = spoken_clarify("asdfkj whale bus")
    assert "asdfkj whale bus" in said.lower()
    assert "sounded like" in said.lower()
    assert "is that what you said" in said.lower()
    note = clarify_speech_note("asdfkj whale bus")
    lowered = note.lower()
    assert "out loud" in lowered or "cannot read" in lowered
    assert "asdfkj whale bus" in lowered
    mapper = RealtimeMapper()
    ui, outbound = mapper.handle(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "asdfkj mmm fff",
        }
    )
    roles = [str(message.get("role")) for message in ui]
    assert "child" in roles
    assert "tutor" in roles
    tutor = next(message for message in ui if message.get("role") == "tutor")
    assert "asdfkj fff" in str(tutor["text"]).lower()
    assert "sounded like" in str(tutor["text"]).lower()
    create = outbound[-1]
    assert create["type"] == "response.create"
    spoken = json.dumps(create).lower()
    assert "asdfkj fff" in spoken
    assert "out loud" in spoken or "speak" in spoken


def test_clear_transcript_does_not_force_a_clarify() -> None:
    mapper = RealtimeMapper()
    _ui, outbound = mapper.handle(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "How big is a blue whale?",
        }
    )
    assert all(
        "sounded like" not in str(item.get("item", {}).get("content", [{}])[0].get("text", "")).lower()
        for item in outbound
        if item.get("type") == "conversation.item.create"
    ) or all(item.get("type") != "conversation.item.create" for item in outbound)


def test_paused_video_note_tells_the_tutor_to_listen() -> None:
    text = paused_video_note()
    lowered = text.lower()
    assert "paused" in lowered
    assert "picture" in lowered or "show_picture" in lowered
    assert "keep watching" in lowered or "resume" in lowered
    assert "stop" in lowered


def test_video_control_resume_waits_to_speak_then_resumes() -> None:
    mapper = RealtimeMapper()
    ui, outbound = mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "r1",
            "name": "video_control",
            "arguments": '{"action":"resume"}',
        },
        execute=lambda _name, _args: {"action": "resume", "deferred": False},
    )
    assert all(message.get("type") != "video" for message in ui)
    first_done, _ = mapper.handle({"type": "response.done"})
    assert all(message.get("type") != "video" for message in first_done)
    spoken_done, _ = mapper.handle({"type": "response.done"})
    assert spoken_done[0]["type"] == "video"
    assert spoken_done[0]["action"] == "resume"
    assert outbound[-1]["type"] == "response.create"


def test_video_control_stop_closes_the_player() -> None:
    mapper = RealtimeMapper()
    ui, outbound = mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "s1",
            "name": "video_control",
            "arguments": '{"action":"stop"}',
        },
        execute=lambda _name, _args: {"action": "stop", "deferred": False},
    )
    assert ui[0]["type"] == "video"
    assert ui[0]["action"] == "stop"
    assert outbound[-1]["type"] == "response.create"


def test_spoken_instructions_prefer_stretch_educational_videos() -> None:
    text = spoken_child_instructions("charter", "age-6", "Arum")
    lowered = text.lower()
    assert "history" in lowered or "science" in lowered
    assert "educational" in lowered
    assert "briefing" in lowered or "six-year-old" in lowered
    assert "paused" in lowered
    assert "keep watching" in lowered or "resume" in lowered
    assert "um" in lowered
    assert "is that what you said" in lowered


def test_spoken_instructions_sound_like_a_person_not_a_safety_officer() -> None:
    text = spoken_child_instructions("charter", "age-6", "Arum")
    lowered = text.lower()
    assert "do not say" in lowered
    assert "safe" in lowered
    assert "vetted" in lowered or "vetting" in lowered
    assert "put on" in lowered


def test_search_and_vet_calls_run_execute_without_video_ui() -> None:
    seen: list[tuple[str, dict[str, object]]] = []

    def execute(name: str, args: dict[str, object]) -> dict[str, object]:
        seen.append((name, args))
        if name == "search_videos":
            return {"candidates": [{"video_id": "abcdefghijk", "title": "Dinosaurs"}]}
        return {"verdict": "approved", "level": 3}

    mapper = RealtimeMapper()
    search_ui, search_out = mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "s1",
            "name": "search_videos",
            "arguments": '{"query":"dinosaur"}',
        },
        execute=execute,
    )
    vet_ui, vet_out = mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "v1",
            "name": "vet_video",
            "arguments": '{"video_id":"abcdefghijk"}',
        },
        execute=execute,
    )
    assert seen == [
        ("search_videos", {"query": "dinosaur"}),
        ("vet_video", {"video_id": "abcdefghijk"}),
    ]
    assert all(message.get("type") != "video" for message in search_ui + vet_ui)
    assert "abcdefghijk" in search_out[0]["item"]["output"]
    assert "approved" in vet_out[0]["item"]["output"]


def test_play_video_emits_ui_only_when_playing() -> None:
    mapper = RealtimeMapper()
    denied, _ = mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "p1",
            "name": "play_video",
            "arguments": '{"video_id":"notvetted1"}',
        },
        execute=lambda _name, _args: {"error": "video has not passed vetting"},
    )
    assert all(message.get("type") != "video" for message in denied)
    allowed, _ = mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "p2",
            "name": "play_video",
            "arguments": '{"video_id":"abcdefghijk"}',
        },
        execute=lambda _name, _args: {"playing": "abcdefghijk"},
    )
    assert all(message.get("type") != "video" for message in allowed)
    first_done, _ = mapper.handle({"type": "response.done"})
    assert all(message.get("type") != "video" for message in first_done)
    spoken_done, _ = mapper.handle({"type": "response.done"})
    kinds = [str(message.get("type")) for message in spoken_done]
    assert kinds == ["video", "state"]
    assert spoken_done[0]["video_id"] == "abcdefghijk"
    assert spoken_done[0].get("audio_only") in (None, False)
    assert spoken_done[1] == {"type": "state", "name": "listening", "detail": ""}


def test_play_video_can_emit_audio_only() -> None:
    mapper = RealtimeMapper()
    mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "p3",
            "name": "play_video",
            "arguments": '{"video_id":"songid11111","audio_only":true}',
        },
        execute=lambda _name, _args: {"playing": "songid11111", "audio_only": True},
    )
    mapper.handle({"type": "response.done"})
    spoken_done, _ = mapper.handle({"type": "response.done"})
    assert spoken_done[0]["type"] == "video"
    assert spoken_done[0]["video_id"] == "songid11111"
    assert spoken_done[0]["audio_only"] is True


def test_launch_app_stops_the_tutor() -> None:
    mapper = RealtimeMapper()
    ui, outbound = mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "g1",
            "name": "launch_app",
            "arguments": '{"app_id":"gcompris","activity":"enumerate"}',
        },
        execute=lambda _name, _args: {
            "app_id": "gcompris",
            "activity": "enumerate",
            "argv": ["gcompris-qt", "--launch", "enumerate"],
            "pid": 7,
        },
    )
    assert ui[0]["type"] == "launch"
    assert ui[0]["app_id"] == "gcompris"
    assert ui[0]["argv"] == ["gcompris-qt", "--launch", "enumerate"]
    assert any(item.get("type") == "response.cancel" for item in outbound)
    leftover, _ = mapper.handle({"type": "response.output_audio.delta", "delta": "AAAA"})
    assert leftover == []


def test_failed_show_board_does_not_change_the_screen() -> None:
    mapper = RealtimeMapper()
    ui, outbound = mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "b1",
            "name": "show_board",
            "arguments": '{"elements":[{"type":"image","image_id":"dinosaur"}]}',
        },
        execute=lambda _name, _args: {"error": "image is not in the local library"},
    )
    assert all(message.get("type") != "board" for message in ui)
    assert outbound[-1]["type"] == "response.create"


def test_show_picture_waits_to_speak_then_shows_the_image() -> None:
    mapper = RealtimeMapper()
    ui, outbound = mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "p1",
            "name": "show_picture",
            "arguments": '{"topic":"dinosaur"}',
        },
        execute=lambda _name, _args: {"shown": True, "image_id": "dinosaur"},
    )
    assert all(message.get("type") != "picture" for message in ui)
    first_done, _ = mapper.handle({"type": "response.done"})
    assert all(message.get("type") != "picture" for message in first_done)
    assert first_done[-1] == {"type": "state", "name": "thinking", "detail": ""}
    spoken_done, _ = mapper.handle({"type": "response.done"})
    kinds = [str(message.get("type")) for message in spoken_done]
    assert kinds == ["picture", "state"]
    assert spoken_done[0]["image_id"] == "dinosaur"
    assert outbound[-1]["type"] == "response.create"


def test_a_loading_picture_shows_a_placeholder_right_away() -> None:
    mapper = RealtimeMapper()
    ui, outbound = mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "p2",
            "name": "show_picture",
            "arguments": '{"topic":"shark depth"}',
        },
        execute=lambda _name, _args: {"loading": True, "image_id": "shark-depth", "topic": "shark depth"},
    )
    assert ui[0] == {"type": "picture", "image_id": "shark-depth", "loading": True}
    assert outbound[-1]["type"] == "response.create"
    spoken = str(outbound[-1]["response"]["instructions"])
    assert "I'm making you a picture" in spoken
    assert "shark depth" in spoken
    assert "do not repeat" in spoken.lower() or "once" in spoken.lower()


def test_picture_making_line_names_what_the_picture_is_about() -> None:
    line = picture_making_line("pterodactyl")
    assert line == "I'm making you a picture to show you pterodactyl."
    assert "picture" in picture_making_line("").lower()
    wait = picture_wait_instructions("pterodactyl").lower()
    assert "i'm making you a picture" in wait
    assert "do not repeat" in wait or "once" in wait
    assert "do not say hang on" in wait
    assert "do not stop" not in wait


def test_a_loading_picture_keeps_the_tutor_talking_until_it_is_ready() -> None:
    mapper = RealtimeMapper()
    mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "p3",
            "name": "show_picture",
            "arguments": '{"topic":"polar bear"}',
        },
        execute=lambda _name, _args: {"loading": True, "image_id": "polar-bear", "topic": "polar bear"},
    )
    first_done, more = mapper.handle({"type": "response.done"})
    assert first_done[-1] == {"type": "state", "name": "thinking", "detail": ""}
    assert more == []
    leftover, _ = mapper.handle({"type": "response.output_audio.delta", "delta": "QQ=="})
    assert leftover[0]["type"] == "audio_chunk"
    ready_ui, ready_out = mapper.picture_ready()
    assert ready_ui == [{"type": "state", "name": "listening", "detail": ""}]
    assert ready_out == [{"type": "response.cancel"}]
    assert not any(item.get("type") == "response.create" for item in ready_out)
    again_ui, again_out = mapper.picture_ready()
    assert again_ui == []
    assert again_out == []
    dropped, _ = mapper.handle({"type": "response.output_audio.delta", "delta": "QQ=="})
    assert dropped == []
    after, quiet = mapper.handle({"type": "response.done"})
    assert after[-1] == {"type": "state", "name": "listening", "detail": ""}
    assert quiet == []


def test_ask_choice_does_not_show_buttons() -> None:
    mapper = RealtimeMapper()
    ui, outbound = mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "c1",
            "name": "ask_choice",
            "arguments": '{"prompt":"Pick","options":[{"id":"a","label":"A"}]}',
        },
        execute=lambda _name, _args: {"skipped": True},
    )
    assert all(message.get("type") != "choices" for message in ui)
    assert outbound[0]["type"] == "conversation.item.create"


def test_spoken_instructions_forbid_written_menus() -> None:
    text = spoken_child_instructions("charter", "age-6", "Arum")
    assert "Arum" in text
    assert "cannot read" in text.lower()
    assert "ask_choice" in text.lower() or "written" in text.lower()
    assert "spoken" in text.lower()


def test_reset_listen_cancels_speech_and_clears_the_buffer() -> None:
    mapper = RealtimeMapper()
    mapper.child_partial = "um hello"
    mapper.tutor_partial = "Let me tell"
    mapper.pending_video = {"type": "video", "action": "play", "video_id": "abcdefghijk"}
    mapper.hold_video = True
    ui, outbound = mapper.reset_listen()
    assert ui == [{"type": "state", "name": "listening", "detail": ""}]
    assert {"type": "response.cancel"} in outbound
    assert {"type": "input_audio_buffer.clear"} in outbound
    leftover, create = mapper.handle(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "hello dinosaurs",
        }
    )
    assert leftover == []
    assert create == []
    audio, _ = mapper.handle({"type": "response.output_audio.delta", "delta": "AQID"})
    assert audio == []
    done, _ = mapper.handle({"type": "response.done"})
    assert all(item.get("type") != "video" for item in done)


def test_reset_listen_lets_the_next_spoken_turn_through() -> None:
    mapper = RealtimeMapper()
    mapper.reset_listen()
    started, _ = mapper.handle({"type": "input_audio_buffer.speech_started"})
    assert started[0] == {"type": "state", "name": "listening", "detail": "hearing"}
    ui, outbound = mapper.handle(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "how big is a blue whale",
        }
    )
    assert ui[0]["text"] == "how big is a blue whale"
    assert any(item.get("type") == "response.create" for item in outbound)
    mapper.handle({"type": "response.created"})
    audio, _ = mapper.handle({"type": "response.output_audio.delta", "delta": "AQID"})
    assert audio[0]["type"] == "audio_chunk"


def test_reset_listen_sends_cancel_and_clear_on_the_socket() -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, object]] = []

        async def send(self, raw: str) -> None:
            self.sent.append(json.loads(raw))

    async def run() -> None:
        talk = RealtimeTalk(
            api_key="sk-test",
            instructions="help",
            execute=lambda _name, _args: {},
        )
        talk._socket = FakeSocket()
        ui = await talk.reset_listen()
        assert ui[0]["name"] == "listening"
        kinds = [item["type"] for item in talk._socket.sent]
        assert "response.cancel" in kinds
        assert "input_audio_buffer.clear" in kinds

    asyncio.run(run())


def test_set_tutor_name_asks_for_an_instruction_update() -> None:
    def execute(name: str, args: dict[str, object]) -> dict[str, object]:
        return {"name": "Pixel", "update_instructions": True}

    mapper = RealtimeMapper()
    _ui, outbound = mapper.handle(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "c2",
            "name": "set_tutor_name",
            "arguments": '{"name":"Pixel"}',
        },
        execute=execute,
    )
    assert any(item.get("type") == "schoolbook.rename" and item.get("name") == "Pixel" for item in outbound)
    assert any(item.get("type") == "response.create" for item in outbound)


def test_reconnect_opens_a_new_session_with_the_new_voice() -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, object]] = []
            self._incoming = asyncio.Queue[str]()
            self.closed = False

        async def send(self, raw: str) -> None:
            self.sent.append(json.loads(raw))

        async def recv(self) -> str:
            return await self._incoming.get()

        async def close(self) -> None:
            self.closed = True

    sockets: list[FakeSocket] = []

    async def run() -> None:
        async def connect(_key: str) -> FakeSocket:
            socket = FakeSocket()
            sockets.append(socket)
            await socket._incoming.put(json.dumps({"type": "session.created"}))
            return socket

        talk = RealtimeTalk(
            api_key="sk-test",
            instructions="help",
            execute=lambda _name, _args: {},
            connect=connect,
            voice="marin",
        )
        await talk.start()
        await talk.reconnect("cedar")
        assert sockets[0].closed is True
        assert sockets[1].sent[0]["session"]["audio"]["output"]["voice"] == "cedar"

    asyncio.run(run())


def test_start_waits_for_session_created_then_updates() -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, object]] = []
            self._incoming = asyncio.Queue[str]()

        async def send(self, raw: str) -> None:
            self.sent.append(json.loads(raw))

        async def recv(self) -> str:
            return await self._incoming.get()

    async def run() -> None:
        socket = FakeSocket()
        await socket._incoming.put(json.dumps({"type": "session.created"}))

        async def connect(_key: str) -> FakeSocket:
            return socket

        talk = RealtimeTalk(
            api_key="sk-test",
            instructions="help",
            execute=lambda _name, _args: {},
            connect=connect,
        )
        await talk.start()
        assert socket.sent[0]["type"] == "session.update"

    asyncio.run(run())


def test_resample_stretches_16k_pcm_to_24k() -> None:
    pcm = b"\x00\x10\x00\x20"
    out = resample_pcm16(pcm, 16000, 24000)
    assert len(out) == 6
    assert resample_pcm16(pcm, 16000, 16000) == pcm
