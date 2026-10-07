# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""JSON messages for the child WebSocket and the session-agent socket."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from schoolbook_protocol.board import BoardElement


class Hello(BaseModel):
    type: Literal["hello"] = "hello"
    protocol_major: int
    token: str = Field(min_length=1)


class AudioFrame(BaseModel):
    type: Literal["audio_frame"] = "audio_frame"
    turn_id: str
    seq: int = Field(ge=0)
    pcm_b64: str
    sample_rate: int = 16000


class TalkStart(BaseModel):
    type: Literal["talk_start"] = "talk_start"
    turn_id: str


class TalkEnd(BaseModel):
    type: Literal["talk_end"] = "talk_end"
    turn_id: str


class DevText(BaseModel):
    type: Literal["dev_text"] = "dev_text"
    turn_id: str
    text: str = Field(max_length=500)


class ChoiceSelected(BaseModel):
    type: Literal["choice"] = "choice"
    turn_id: str
    option_id: str


class BoardTap(BaseModel):
    type: Literal["board_tap"] = "board_tap"
    turn_id: str
    element_index: int = Field(ge=0)
    index: int = Field(ge=0)


class VideoUi(BaseModel):
    type: Literal["video_ui"] = "video_ui"
    action: Literal["pause", "resume", "done"]


class UnlockGesture(BaseModel):
    type: Literal["unlock_gesture"] = "unlock_gesture"


class GoHome(BaseModel):
    type: Literal["home"] = "home"


class Ping(BaseModel):
    type: Literal["ping"] = "ping"


ClientMessage = Annotated[
    Hello
    | AudioFrame
    | TalkStart
    | TalkEnd
    | DevText
    | ChoiceSelected
    | BoardTap
    | VideoUi
    | UnlockGesture
    | GoHome
    | Ping,
    Field(discriminator="type"),
]


class HelloOk(BaseModel):
    type: Literal["hello_ok"] = "hello_ok"
    protocol_major: int
    learner_name: str


class Transcript(BaseModel):
    type: Literal["transcript"] = "transcript"
    turn_id: str
    role: Literal["child", "tutor"]
    text: str
    partial: bool = False


class BoardCommand(BaseModel):
    type: Literal["board"] = "board"
    turn_id: str
    elements: list[BoardElement]


class ChoiceOption(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=40)


class ChoicePrompt(BaseModel):
    type: Literal["choices"] = "choices"
    turn_id: str
    prompt: str = Field(max_length=120)
    options: list[ChoiceOption] = Field(min_length=2, max_length=4)


class AudioChunk(BaseModel):
    type: Literal["audio_chunk"] = "audio_chunk"
    turn_id: str
    seq: int = Field(ge=0)
    pcm_b64: str
    sample_rate: int = 16000


class VideoCommand(BaseModel):
    type: Literal["video"] = "video"
    action: Literal["play", "pause", "resume", "seek", "stop", "destroy"]
    video_id: str = ""
    start_s: float | None = None
    end_s: float | None = None
    at_s: float | None = None


class StateEvent(BaseModel):
    type: Literal["state"] = "state"
    name: Literal[
        "home",
        "listening",
        "thinking",
        "speaking",
        "board",
        "video",
        "app",
        "offline",
        "parent_unlock",
        "parent_menu",
    ]
    detail: str = ""


class SessionRecap(BaseModel):
    type: Literal["recap"] = "recap"
    text: str


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


class Pong(BaseModel):
    type: Literal["pong"] = "pong"


DaemonMessage = Annotated[
    HelloOk
    | Transcript
    | BoardCommand
    | ChoicePrompt
    | AudioChunk
    | VideoCommand
    | StateEvent
    | SessionRecap
    | ErrorEvent
    | Pong,
    Field(discriminator="type"),
]


class LaunchApp(BaseModel):
    type: Literal["launch"] = "launch"
    app_id: str
    argv: list[str] = Field(min_length=1)


class FocusHome(BaseModel):
    type: Literal["focus_home"] = "focus_home"


class SetObserver(BaseModel):
    type: Literal["set_observer"] = "set_observer"
    enabled: bool
    interval_s: float = 3


class AppStarted(BaseModel):
    type: Literal["app_started"] = "app_started"
    app_id: str
    pid: int


class AppExited(BaseModel):
    type: Literal["app_exited"] = "app_exited"
    app_id: str
    code: int


class UnlockRequested(BaseModel):
    type: Literal["unlock_requested"] = "unlock_requested"


class ScreenFrame(BaseModel):
    type: Literal["screen_frame"] = "screen_frame"
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    gray_b64: str
    captured_at_ms: int


class PlaybackAudio(BaseModel):
    type: Literal["playback_audio"] = "playback_audio"
    pcm_b64: str
    sample_rate: int = 16000
    at_ms: int = 0


SessionMessage = Annotated[
    LaunchApp
    | FocusHome
    | SetObserver
    | AppStarted
    | AppExited
    | UnlockRequested
    | ScreenFrame
    | PlaybackAudio,
    Field(discriminator="type"),
]


_client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
_daemon_adapter: TypeAdapter[DaemonMessage] = TypeAdapter(DaemonMessage)
_session_adapter: TypeAdapter[SessionMessage] = TypeAdapter(SessionMessage)


def parse_client_message(payload: object) -> ClientMessage:
    return _client_adapter.validate_python(payload)


def parse_daemon_message(payload: object) -> DaemonMessage:
    return _daemon_adapter.validate_python(payload)


def parse_session_message(payload: object) -> SessionMessage:
    return _session_adapter.validate_python(payload)
