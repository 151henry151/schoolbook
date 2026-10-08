# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

import asyncio
import json

from schoolbookd.providers.openai_realtime import (
    REALTIME_TOOLS,
    RealtimeMapper,
    RealtimeTalk,
    clarify_speech_note,
    connect_headers,
    looks_like_child_speech,
    paused_video_note,
    resample_pcm16,
    session_update,
    spoken_child_instructions,
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
    assert session["tools"][0]["name"] == "show_board"


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


def test_child_transcript_deltas_stream_before_the_final() -> None:
    mapper = RealtimeMapper()
    first, outbound = mapper.handle(
        {"type": "conversation.item.input_audio_transcription.delta", "delta": "Show"}
    )
    second, _ = mapper.handle(
        {"type": "conversation.item.input_audio_transcription.delta", "delta": " me"}
    )
    assert first[0]["role"] == "child"
    assert first[0]["text"] == "Show"
    assert first[0]["partial"] is True
    assert second[0]["text"] == "Show me"
    assert outbound == []


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
    assert "video_control" in names
    assert "show_picture" in names


def test_spoken_instructions_tell_the_tutor_to_find_videos_itself() -> None:
    text = spoken_child_instructions("charter", "age-6", "Arum")
    lowered = text.lower()
    assert "search_videos" in text
    assert "vet_video" in text
    assert "play_video" in text
    assert "video id" in lowered or "video_id" in lowered
    assert "never ask" in lowered
    assert "show_picture" in text


def test_looks_like_child_speech_rejects_garbled_words() -> None:
    assert looks_like_child_speech("How big is a blue whale next to a school bus?")
    assert looks_like_child_speech("Show me a dinosaur.")
    assert looks_like_child_speech("yes")
    assert looks_like_child_speech("T rex")
    assert not looks_like_child_speech("")
    assert not looks_like_child_speech("...")
    assert not looks_like_child_speech("asdfkj mmm fff")
    assert not looks_like_child_speech("blargh zzzz qkpt")


def test_unclear_transcript_asks_the_child_to_confirm() -> None:
    note = clarify_speech_note("asdfkj whale bus")
    lowered = note.lower()
    assert "asdfkj whale bus" in lowered
    assert "sounded like" in lowered
    assert "is that what you said" in lowered
    mapper = RealtimeMapper()
    ui, outbound = mapper.handle(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "asdfkj mmm fff",
        }
    )
    assert ui[0]["text"] == "asdfkj mmm fff"
    assert outbound[0]["type"] == "conversation.item.create"
    briefing = str(outbound[0]["item"]["content"][0]["text"])
    assert "sounded like" in briefing.lower()
    assert "asdfkj mmm fff" in briefing.lower()
    assert outbound[-1]["type"] == "response.create"


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
    assert "sounded like" in lowered


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
    assert spoken_done[1] == {"type": "state", "name": "listening", "detail": ""}


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
    spoken_done, _ = mapper.handle({"type": "response.done"})
    kinds = [str(message.get("type")) for message in spoken_done]
    assert kinds == ["picture", "state"]
    assert spoken_done[0]["image_id"] == "dinosaur"
    assert outbound[-1]["type"] == "response.create"


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
