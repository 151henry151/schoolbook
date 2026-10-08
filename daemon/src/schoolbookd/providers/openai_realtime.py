# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""OpenAI Realtime speech-to-speech. Tests inject a mapper; the socket is optional."""

from __future__ import annotations

import array
import json
import re
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
                "When the child asks to watch something, treat it as a parent briefing: "
                "you have a six-year-old who wants a video about that topic. "
                "Pick something educational that teaches history or science of the topic, "
                "then call search_videos, vet_video, and play_video. "
                "Say you will put on a video about that thing. "
                "If the child wants a picture, call show_picture with the topic. "
                "Do not call show_board with a made-up image_id. "
                "When searching videos, use a short query like dinosaur fossils. "
                "Search once, vet the best candidate, and play it. Do not talk between those tools. "
                "If the child's words do not make sense, say: "
                "It sounded like you said those words. Is that what you said? Then wait. Do not guess. "
                "If a video is paused and the child talks, listen. "
                "If they ask a question about the video, answer it and call show_picture if a picture helps. "
                "Then ask if they want to keep watching. "
                "If they say yes, call video_control resume. If they say no, call video_control stop. "
                "For a different video, search and play a new one. "
                "Never ask the child or a grown-up for a video ID. "
                "Do not say safe, vetted, approved, or mention a video ID out loud."
            ),
        ]
    )


OUTPUT_RATE = 24000
INPUT_RATE = 24000

_TOPIC_PATTERNS = (
    re.compile(
        r"(?:show me|can i (?:see|watch)|i want (?:to )?(?:see|watch)|watch|put on)\s+"
        r"(?:some |a |an )?(.+?)\s+videos?\b",
        re.I,
    ),
    re.compile(r"(?:videos?|movies?|films?)\s+(?:of|about|on)\s+(.+)", re.I),
    re.compile(
        r"(?:show me|watch|put on)\s+(?:a |an |some )?(?:video|movie|film)s?\s+(?:of|about|on)?\s*(.+)",
        re.I,
    ),
)


def video_topic(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None
    for pattern in _TOPIC_PATTERNS:
        match = pattern.search(stripped)
        if match:
            topic = match.group(1).strip(" .?!,")
            topic = re.sub(r"^(some|a|an|the)\s+", "", topic, flags=re.I)
            if topic:
                return topic
    return None


_SHORT_OK = {"a", "i", "no", "yes", "ok", "hi", "hey", "wow", "why", "how", "who", "what"}


def looks_like_child_speech(text: str) -> bool:
    words = re.findall(r"[a-zA-Z']+", text or "")
    if not words:
        return False
    real = 0
    for word in words:
        low = word.lower()
        if low in _SHORT_OK or (len(low) >= 3 and re.search(r"[aeiouy]", low)):
            real += 1
    return real > 0 and real / len(words) >= 0.5


def clarify_speech_note(text: str) -> str:
    heard = " ".join((text or "").split())
    if not heard:
        return (
            "The child's words were not clear. "
            "Say you did not catch that and ask them to say it again. Do not guess."
        )
    return (
        f'It sounded like the child said: "{heard}". That may be wrong. '
        f"Ask out loud: It sounded like you said {heard}. Is that what you said? "
        "Then wait. Do not start a video, picture, or new topic until they confirm or say it again."
    )


def paused_video_note() -> str:
    return (
        "The child paused the video. It is still there, paused. Listen. "
        "If they ask a question about the video, answer it. Call show_picture if a picture helps. "
        "Then ask if they want to keep watching. "
        "If they say yes, call video_control resume. Do not start the video over. "
        "If they say no, or want something else, call video_control stop and then help them. "
        "If they want a different video, search, vet, and play a new one."
    )


def video_watch_briefing(child_text: str, *, name: str = "the child") -> str | None:
    topic = video_topic(child_text)
    if topic is None:
        return None
    return (
        f"You have a six-year-old named {name} who wants to watch a video about {topic}. "
        f"Pick something educational that will teach him something good about the history of {topic} "
        f"or the science behind {topic}. Pick out a good educational video from YouTube and play it. "
        f"Do not pick a baby song, nursery cartoon, or Cocomelon-style show. "
        f"When you speak to him, just say you will put on a video about {topic}."
    )

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
                        "create_response": False,
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
            "Search YouTube for a high-quality educational video about the child's topic, "
            "aimed at ages 10-12. Prefer documentaries and explainers. "
            "Do not pick baby songs or nursery cartoons. Returns candidate video_id values. "
            "Never ask anyone for a video ID."
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
    {
        "type": "function",
        "name": "video_control",
        "description": "Pause, resume, or stop the video that is on screen. Use stop when the child wants to do something else.",
        "parameters": {
            "type": "object",
            "properties": {"action": {"type": "string", "enum": ["pause", "resume", "stop"]}},
            "required": ["action"],
        },
    },
    {
        "type": "function",
        "name": "show_picture",
        "description": (
            "Make an educational picture of the child's topic and show it. "
            "Use this instead of show_board when they ask to see what something looks like."
        ),
        "parameters": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
]


@dataclass
class RealtimeMapper:
    turn_id: str = "live"
    seq: int = 0
    child_name: str = "Arum"
    pending_video: dict[str, object] | None = None
    hold_video: bool = False
    pending_picture: dict[str, object] | None = None
    hold_picture: bool = False
    child_partial: str = ""
    tutor_partial: str = ""

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
            self.child_partial = ""
            return ([{"type": "state", "name": "listening", "detail": "hearing"}], [])
        if kind == "input_audio_buffer.speech_stopped":
            return ([{"type": "state", "name": "thinking", "detail": ""}], [])
        if kind == "response.done":
            messages: list[dict[str, object]] = []
            if self.pending_video is not None and self.hold_video:
                self.hold_video = False
            elif self.pending_video is not None:
                messages.append(self.pending_video)
                self.pending_video = None
            if self.pending_picture is not None and self.hold_picture:
                self.hold_picture = False
            elif self.pending_picture is not None:
                messages.append(self.pending_picture)
                self.pending_picture = None
            messages.append({"type": "state", "name": "listening", "detail": ""})
            return (messages, [])
        if kind == "conversation.item.input_audio_transcription.delta":
            piece = str(event.get("delta") or event.get("transcript") or "")
            if not piece:
                return ([], [])
            self.child_partial += piece
            return (
                [
                    {
                        "type": "transcript",
                        "turn_id": self.turn_id,
                        "role": "child",
                        "text": self.child_partial,
                        "partial": True,
                    }
                ],
                [],
            )
        if kind in {"response.output_audio_transcript.delta", "response.audio_transcript.delta"}:
            piece = str(event.get("delta") or event.get("transcript") or "")
            if not piece:
                return ([], [])
            self.tutor_partial += piece
            return (
                [
                    {
                        "type": "transcript",
                        "turn_id": self.turn_id,
                        "role": "tutor",
                        "text": self.tutor_partial,
                        "partial": True,
                    }
                ],
                [],
            )
        if kind == "conversation.item.input_audio_transcription.failed":
            return (
                [],
                [
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "system",
                            "content": [{"type": "input_text", "text": clarify_speech_note("")}],
                        },
                    },
                    {"type": "response.create"},
                ],
            )
        if kind == "conversation.item.input_audio_transcription.completed":
            text = str(event.get("transcript", "")).strip() or self.child_partial.strip()
            self.child_partial = ""
            outbound: list[dict[str, object]] = []
            if text and not looks_like_child_speech(text):
                outbound.append(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "system",
                            "content": [{"type": "input_text", "text": clarify_speech_note(text)}],
                        },
                    }
                )
            else:
                briefing = video_watch_briefing(text, name=self.child_name) if text else None
                if briefing:
                    outbound.append(
                        {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "system",
                                "content": [{"type": "input_text", "text": briefing}],
                            },
                        }
                    )
            outbound.append({"type": "response.create"})
            if not text:
                return ([], outbound)
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
                outbound,
            )
        if kind in {"response.audio_transcript.done", "response.output_audio_transcript.done"}:
            text = str(event.get("transcript", "")).strip() or self.tutor_partial.strip()
            self.tutor_partial = ""
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
        if name == "show_board" and "error" not in result:
            elements = args.get("elements")
            if isinstance(elements, list):
                ui.append({"type": "board", "turn_id": self.turn_id, "elements": elements})
        elif name == "show_picture" and result.get("image_id") and "error" not in result:
            self.pending_picture = {"type": "picture", "image_id": str(result["image_id"])}
            self.hold_picture = True
        elif name == "play_video" and "playing" in result and "error" not in result:
            self.pending_video = {
                "type": "video",
                "action": "play",
                "video_id": str(result.get("playing") or args.get("video_id", "")),
                "start_s": None,
                "end_s": None,
                "at_s": None,
            }
            self.hold_video = True
        elif name == "video_control" and "error" not in result:
            action = str(args.get("action"))
            if action == "stop":
                ui.append(
                    {
                        "type": "video",
                        "action": "stop",
                        "video_id": "",
                        "start_s": None,
                        "end_s": None,
                        "at_s": None,
                    }
                )
            elif action == "resume":
                self.pending_video = {
                    "type": "video",
                    "action": "resume",
                    "video_id": "",
                    "start_s": None,
                    "end_s": None,
                    "at_s": None,
                }
                self.hold_video = True
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

    async def add_system_note(self, text: str) -> None:
        if self._socket is None or not text.strip():
            return
        await self._socket.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "system",
                        "content": [{"type": "input_text", "text": text}],
                    },
                }
            )
        )

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
