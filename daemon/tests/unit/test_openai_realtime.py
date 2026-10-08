# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

import asyncio
import json

from schoolbookd.providers.openai_realtime import (
    REALTIME_TOOLS,
    RealtimeMapper,
    RealtimeTalk,
    connect_headers,
    resample_pcm16,
    session_update,
    spoken_child_instructions,
)


def test_session_update_disables_barge_in_and_uses_server_vad() -> None:
    payload = session_update(instructions="Be a computer helper.", tools=[{"name": "show_board"}])
    session = payload["session"]
    assert payload["type"] == "session.update"
    assert session["instructions"] == "Be a computer helper."
    turn = session["audio"]["input"]["turn_detection"]
    assert turn["type"] == "server_vad"
    assert turn["interrupt_response"] is False
    assert turn["create_response"] is True
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


def test_child_transcript_is_forwarded() -> None:
    mapper = RealtimeMapper()
    ui, _ = mapper.handle(
        {"type": "conversation.item.input_audio_transcription.completed", "transcript": "hello"}
    )
    assert ui[0]["type"] == "transcript"
    assert ui[0]["role"] == "child"
    assert ui[0]["text"] == "hello"


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


def test_spoken_instructions_tell_the_tutor_to_find_videos_itself() -> None:
    text = spoken_child_instructions("charter", "age-6", "Arum")
    lowered = text.lower()
    assert "search_videos" in text
    assert "vet_video" in text
    assert "play_video" in text
    assert "video id" in lowered or "video_id" in lowered
    assert "never ask" in lowered


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
    assert allowed[0]["type"] == "video"
    assert allowed[0]["video_id"] == "abcdefghijk"


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
