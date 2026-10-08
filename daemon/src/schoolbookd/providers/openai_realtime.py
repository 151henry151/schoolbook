# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""OpenAI Realtime speech-to-speech. Tests inject a mapper; the socket is optional."""

from __future__ import annotations

import array
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

REALTIME_MODEL = "gpt-realtime-2.1"
REALTIME_URL = f"wss://api.openai.com/v1/realtime?model={REALTIME_MODEL}"


def connect_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def spoken_child_instructions(core: str, age_text: str, name: str) -> str:
    return "\n\n".join(
        [
            core.strip(),
            age_text.strip(),
            (
                f"The child's name is {name}. He is six and cannot read yet. "
                "Every reply must be spoken out loud. Never show written menus, buttons, or choice lists. "
                "Do not call ask_choice. Ask one spoken question and wait. "
                "Pictures and videos are fine. Keep turns short and warm. "
                "Talk the way a kind person talks to a six-year-old. "
                "When the child asks to watch something, say you will put on a video about that thing, "
                "then call search_videos, then vet_video, then play_video. "
                "Never ask the child or a grown-up for a video ID. "
                "Do not say safe, vetted, approved, or mention a video ID out loud."
            ),
        ]
    )


OUTPUT_RATE = 24000
INPUT_RATE = 24000

Execute = Callable[[str, dict[str, object]], dict[str, object]]
Emit = Callable[[dict[str, object]], Awaitable[None]]


def resample_pcm16(pcm: bytes, from_rate: int, to_rate: int) -> bytes:
    if from_rate == to_rate or not pcm:
        return pcm
    src = array.array("h")
    src.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not src:
        return b""
    ratio = to_rate / from_rate
    length = int(len(src) * ratio)
    out = array.array("h")
    last = len(src) - 1
    for index in range(length):
        pos = index / ratio
        lo = int(pos)
        hi = min(lo + 1, last)
        frac = pos - lo
        out.append(int(src[lo] * (1.0 - frac) + src[hi] * frac))
    return out.tobytes()


def session_update(*, instructions: str, tools: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": REALTIME_MODEL,
            "instructions": instructions,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": INPUT_RATE},
                    "turn_detection": {
                        "type": "server_vad",
                        "create_response": True,
                        "interrupt_response": False,
                        "silence_duration_ms": 700,
                    },
                    "transcription": {"model": "gpt-4o-mini-transcribe"},
                },
                "output": {
                    "format": {"type": "audio/pcm", "rate": OUTPUT_RATE},
                    "voice": "marin",
                },
            },
            "tools": tools,
        },
    }


REALTIME_TOOLS: list[dict[str, object]] = [
    {
        "type": "function",
        "name": "show_board",
        "description": "Show words, numbers, or pictures on the child's board.",
        "parameters": {
            "type": "object",
            "properties": {"elements": {"type": "array", "items": {"type": "object"}}},
            "required": ["elements"],
        },
    },
    {
        "type": "function",
        "name": "search_videos",
        "description": (
            "Search YouTube for a video the child asked to watch. "
            "Returns candidate video_id values. Never ask anyone for a video ID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "subject": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "vet_video",
        "description": "Run the vetting pipeline on a video_id from search_videos. Must pass before play_video.",
        "parameters": {
            "type": "object",
            "properties": {"video_id": {"type": "string"}},
            "required": ["video_id"],
        },
    },
    {
        "type": "function",
        "name": "play_video",
        "description": "Play a video_id that just passed vet_video. Search and vet first; never ask for an ID.",
        "parameters": {
            "type": "object",
            "properties": {"video_id": {"type": "string"}},
            "required": ["video_id"],
        },
    },
]


@dataclass
class RealtimeMapper:
    turn_id: str = "live"
    seq: int = 0

    def append_audio(self, pcm_b64: str) -> dict[str, object]:
        return {"type": "input_audio_buffer.append", "audio": pcm_b64}

    def handle(
        self,
        event: dict[str, object],
        execute: Execute | None = None,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        kind = str(event.get("type", ""))
        if kind in {"response.output_audio.delta", "response.audio.delta"}:
            delta = str(event.get("delta", ""))
            chunk = {
                "type": "audio_chunk",
                "turn_id": self.turn_id,
                "seq": self.seq,
                "pcm_b64": delta,
                "sample_rate": OUTPUT_RATE,
            }
            self.seq += 1
            return ([chunk], [])
        if kind == "error":
            return ([{"type": "state", "name": "listening", "detail": ""}], [])
        if kind == "input_audio_buffer.speech_started":
            return ([{"type": "state", "name": "listening", "detail": "hearing"}], [])
        if kind == "input_audio_buffer.speech_stopped":
            return ([{"type": "state", "name": "thinking", "detail": ""}], [])
        if kind == "response.done":
            return ([{"type": "state", "name": "listening", "detail": ""}], [])
        if kind == "conversation.item.input_audio_transcription.completed":
            text = str(event.get("transcript", "")).strip()
            if not text:
                return ([], [])
            return (
                [
                    {
                        "type": "transcript",
                        "turn_id": self.turn_id,
                        "role": "child",
                        "text": text,
                        "partial": False,
                    }
                ],
                [],
            )
        if kind in {"response.audio_transcript.done", "response.output_audio_transcript.done"}:
            text = str(event.get("transcript", "")).strip()
            if not text:
                return ([], [])
            return (
                [
                    {
                        "type": "transcript",
                        "turn_id": self.turn_id,
                        "role": "tutor",
                        "text": text,
                        "partial": False,
                    }
                ],
                [],
            )
        if kind == "response.function_call_arguments.done":
            return self._function_call(event, execute)
        if kind == "response.output_item.done":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "function_call":
                return self._function_call(item, execute)
        return ([], [])

    def _function_call(
        self,
        event: dict[str, object],
        execute: Execute | None,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        name = str(event.get("name", ""))
        call_id = str(event.get("call_id", "call"))
        raw_args = event.get("arguments", "{}")
        try:
            args = json.loads(str(raw_args))
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        if name == "ask_choice":
            result: dict[str, object] = {"skipped": True, "reason": "speak the choice out loud"}
        elif execute is not None:
            result = execute(name, args)
        else:
            result = {"error": "no tool runner"}
        ui: list[dict[str, object]] = []
        if name == "show_board":
            elements = args.get("elements")
            if isinstance(elements, list):
                ui.append({"type": "board", "turn_id": self.turn_id, "elements": elements})
        elif name == "play_video" and "playing" in result and "error" not in result:
            ui.append(
                {
                    "type": "video",
                    "action": "play",
                    "video_id": str(result.get("playing") or args.get("video_id", "")),
                    "start_s": None,
                    "end_s": None,
                    "at_s": None,
                }
            )
        outbound: list[dict[str, object]] = [
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                },
            },
            {"type": "response.create"},
        ]
        return (ui, outbound)


Connect = Callable[[str], Awaitable[Any]]


@dataclass
class RealtimeTalk:
    api_key: str
    instructions: str
    execute: Execute
    connect: Connect | None = None
    mapper: RealtimeMapper = field(default_factory=RealtimeMapper)
    tools: list[dict[str, object]] = field(default_factory=lambda: list(REALTIME_TOOLS))
    _socket: Any = None

    async def start(self) -> None:
        opener = self.connect or _default_connect
        self._socket = await opener(self.api_key)
        raw = await self._socket.recv()
        if isinstance(raw, bytes):
            raw = raw.decode()
        created = json.loads(raw)
        if not isinstance(created, dict) or created.get("type") != "session.created":
            raise RuntimeError(f"realtime handshake failed: {created}")
        await self._socket.send(json.dumps(session_update(instructions=self.instructions, tools=self.tools)))

    async def append_pcm16(self, pcm: bytes, sample_rate: int = 16000) -> None:
        import base64

        if self._socket is None:
            return
        stretched = resample_pcm16(pcm, sample_rate, INPUT_RATE)
        payload = self.mapper.append_audio(base64.b64encode(stretched).decode("ascii"))
        await self._socket.send(json.dumps(payload))

    async def pump(self, emit: Emit) -> None:
        if self._socket is None:
            return
        async for raw in self._socket:
            if isinstance(raw, bytes):
                raw = raw.decode()
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            ui, outbound = self.mapper.handle(event, execute=self.execute)
            for message in ui:
                await emit(message)
            for outgoing in outbound:
                await self._socket.send(json.dumps(outgoing))

    async def close(self) -> None:
        socket = self._socket
        self._socket = None
        if socket is not None:
            closer = getattr(socket, "close", None)
            if closer is not None:
                result = closer()
                if hasattr(result, "__await__"):
                    await result


async def _default_connect(api_key: str) -> Any:
    import websockets

    return await websockets.connect(
        REALTIME_URL,
        additional_headers=connect_headers(api_key),
        max_size=None,
    )
