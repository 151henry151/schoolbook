# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Child WebSocket and parent console HTTP API."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from starlette.responses import Response as StarletteResponse

from schoolbook_protocol.messages import parse_client_message
from schoolbook_protocol.version import MAJOR
from schoolbookd.backup import restic_backup_command
from schoolbookd.db.models import (
    ContentRequest,
    Flag,
    ImageRow,
    Interest,
    Note,
    Observation,
    SessionRow,
    Skill,
    SkillState,
    ToolCall,
    Turn,
    Video,
)
from schoolbookd.policy.unlock import UnlockState, attempt_unlock, hash_password
from schoolbookd.providers.base import STTProvider
from schoolbookd.providers.openai_realtime import (
    DEFAULT_TUTOR_NAME,
    DEFAULT_TUTOR_VOICE,
    REALTIME_TOOLS,
    RealtimeMapper,
    RealtimeTalk,
    paused_video_note,
    spoken_child_instructions,
)
from schoolbookd.runtime import LiveState, Runtime
from schoolbookd.secrets_file import upsert_secrets
from schoolbookd.tutor.loop import TurnOutcome
from schoolbookd.voice.pipeline import (
    ListenBuffer,
    append_pcm,
    encode_audio,
    sentence_audio,
    transcribe_buffer,
)

LOCALHOSTS = {"127.0.0.1", "::1", "testclient", "localhost"}


def _sign(secret: str, expires: float) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": expires}).encode()).decode()
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{digest}"


def _valid(secret: str, token: str, now: float) -> bool:
    payload, _, digest = token.partition(".")
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, digest):
        return False
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
    except (ValueError, json.JSONDecodeError):
        return False
    return float(data.get("exp", 0)) > now


@dataclass
class Host:
    runtime: Runtime
    learner_id: str
    token: str
    password_hash: str
    session_secret: str
    dev_text: bool = False
    lan_enabled: bool = False
    unlock: UnlockState = field(default_factory=UnlockState)
    attempts: list[float] = field(default_factory=list)
    live: LiveState | None = None
    stt: STTProvider | None = None
    buffers: dict[str, ListenBuffer] = field(default_factory=dict)
    cancelled_turns: set[str] = field(default_factory=set)
    speaking_turn: str | None = None
    parent_seen_at: float = 0.0
    parent_locked: bool = False
    idle_lock_s: float = 300
    secrets_path: Path | None = None
    backup_repository: str | None = None
    data_dir: Path | None = None
    voice: str = "pipeline"
    openai_api_key: str = ""

    def request_kiosk_end(self) -> None:
        if self.data_dir is None:
            return
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "kiosk.end").write_text("end\n", encoding="utf-8")

    def ensure_live(self) -> LiveState:
        if self.live is None or self.runtime.store.open_session(self.learner_id) is None:
            session_id = self.runtime.store.start_session(self.learner_id, self.runtime.model)
            self.live = LiveState(session_id=session_id, learner_id=self.learner_id)
        assert self.live is not None
        return self.live

    def login(self, password: str, now: float) -> tuple[bool, str]:
        recent = [stamp for stamp in self.attempts if now - stamp < 300]
        self.attempts = recent
        if len(recent) >= 10:
            return False, "rate limited"
        self.attempts.append(now)
        ok, self.unlock = attempt_unlock(password, self.password_hash, self.unlock, _as_datetime(now))
        if not ok:
            return False, "locked" if self.unlock.locked_until else "invalid password"
        self.parent_seen_at = now
        self.parent_locked = False
        return True, _sign(self.session_secret, now + 3600)

    def begin_talk(self, turn_id: str) -> None:
        if self.speaking_turn:
            self.cancelled_turns.add(self.speaking_turn)
            self.speaking_turn = None
        self.buffers[turn_id] = ListenBuffer()

    def add_audio(self, turn_id: str, pcm_b64: str) -> None:
        buffer = self.buffers.setdefault(turn_id, ListenBuffer())
        append_pcm(buffer, pcm_b64)

    def finish_talk(self, turn_id: str) -> list[dict[str, object]]:
        buffer = self.buffers.pop(turn_id, ListenBuffer())
        if turn_id in self.cancelled_turns:
            return []
        learner = self.runtime.store.learner(self.learner_id)
        hints = [learner.first_name] if learner else []
        if self.stt is None:
            text = ""
        else:
            text, _confidence = transcribe_buffer(self.stt, buffer, hints)
        outcome = self.runtime.child_turn(self.ensure_live(), text)
        if turn_id in self.cancelled_turns:
            return [{"type": "state", "name": "listening", "detail": "interrupted"}]
        self.speaking_turn = turn_id
        messages = _ws_messages(outcome, turn_id)
        if text.strip():
            messages.insert(
                0,
                {"type": "transcript", "turn_id": turn_id, "role": "child", "text": text, "partial": False},
            )
        if outcome.sentences == ["The tutor is resting."]:
            messages.insert(0, {"type": "state", "name": "offline", "detail": "apps"})
        rate = int(getattr(self.runtime.tts, "sample_rate", 16000))
        for seq, pcm in enumerate(sentence_audio(self.runtime.tts, outcome.sentences)):
            if turn_id in self.cancelled_turns:
                break
            messages.append(
                {
                    "type": "audio_chunk",
                    "turn_id": turn_id,
                    "seq": seq,
                    "pcm_b64": encode_audio(pcm),
                    "sample_rate": rate,
                }
            )
        self.speaking_turn = None
        messages.append({"type": "state", "name": "listening", "detail": ""})
        return messages

    def make_realtime(self) -> RealtimeTalk:
        from schoolbookd.tutor.prompts import render_age_profile

        learner = self.runtime.store.learner(self.learner_id)
        name = learner.first_name if learner else "friend"
        stored_voice = self.runtime.store.get_setting("tutor_voice", DEFAULT_TUTOR_VOICE)
        voice = stored_voice if isinstance(stored_voice, str) else DEFAULT_TUTOR_VOICE
        stored_name = self.runtime.store.get_setting("tutor_name", DEFAULT_TUTOR_NAME)
        if isinstance(stored_name, str) and stored_name.strip():
            tutor_name = stored_name
        else:
            tutor_name = DEFAULT_TUTOR_NAME
        instructions = spoken_child_instructions(
            self.runtime.core_prompt,
            render_age_profile(self.runtime.age_profile),
            name,
            tutor_name=tutor_name,
        )

        def execute(tool: str, args: dict[str, object]) -> dict[str, object]:
            return self.runtime.run_tool(self.ensure_live(), tool, args)

        return RealtimeTalk(
            api_key=self.openai_api_key,
            instructions=instructions,
            execute=execute,
            tools=list(REALTIME_TOOLS),
            mapper=RealtimeMapper(child_name=name),
            voice=voice,
            tutor_name=tutor_name,
        )

    def note_transcript(self, role: str, text: str) -> None:
        if not text.strip():
            return
        live = self.ensure_live()
        self.runtime.store.add_turn(live.session_id, role, text)


def _as_datetime(stamp: float) -> datetime:
    return datetime.fromtimestamp(stamp, UTC)


def _local_only(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in LOCALHOSTS


def child_app(host: Host) -> FastAPI:
    app = FastAPI(title="Schoolbook child")

    @app.middleware("http")
    async def localhost(
        request: Request, call_next: Callable[[Request], Awaitable[StarletteResponse]]
    ) -> StarletteResponse:
        if not _local_only(request):
            return JSONResponse({"error": "child UI is local only"}, status_code=403)
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/token")
    def token() -> dict[str, str]:
        return {"token": host.token, "protocol_major": str(MAJOR)}

    @app.get("/pictures/{image_id}")
    def picture(image_id: str) -> StarletteResponse:
        path = host.runtime.image_path(image_id)
        if path is None:
            return JSONResponse({"error": "missing"}, status_code=404)
        return FileResponse(path)

    @app.post("/dev/turn")
    def dev_turn(body: dict[str, str], request: Request) -> JSONResponse:
        if not host.dev_text:
            return JSONResponse({"error": "dev text is off"}, status_code=404)
        if request.headers.get("x-schoolbook-token") != host.token:
            return JSONResponse({"error": "bad token"}, status_code=401)
        outcome = host.runtime.child_turn(host.ensure_live(), body.get("text", ""))
        return JSONResponse(_outcome_payload(outcome))

    @app.post("/unlock")
    def unlock(body: dict[str, str], request: Request) -> JSONResponse:
        if request.headers.get("x-schoolbook-token") != host.token:
            return JSONResponse({"error": "bad token"}, status_code=401)
        ok, _detail = host.login(body.get("password", ""), time.time())
        if not ok:
            return JSONResponse({"error": _detail}, status_code=401)
        ended = body.get("action") == "end"
        if ended:
            host.request_kiosk_end()
        return JSONResponse(
            {"ok": True, "menu": ["console", "pause", "end", "logout", "shutdown"], "ended": ended}
        )

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        if socket.client and socket.client.host not in LOCALHOSTS:
            await socket.close(code=4403)
            return
        await socket.accept()
        raw = await socket.receive_json()
        try:
            hello = parse_client_message(raw)
        except Exception:
            await socket.send_json({"type": "error", "message": "bad hello"})
            await socket.close()
            return
        if hello.type != "hello" or hello.token != host.token or hello.protocol_major != MAJOR:
            await socket.send_json({"type": "error", "message": "unauthorized"})
            await socket.close()
            return
        learner = host.runtime.store.learner(host.learner_id)
        name = learner.first_name if learner else ""
        talk_mode = learner.talk_mode if learner else "handsfree"
        await socket.send_json(
            {
                "type": "hello_ok",
                "protocol_major": MAJOR,
                "learner_name": name,
                "talk_mode": talk_mode,
                "voice": host.voice,
            }
        )
        talk: RealtimeTalk | None = None
        pump: asyncio.Task[None] | None = None
        if host.voice == "realtime" and host.openai_api_key:
            talk = host.make_realtime()

            async def emit(message: dict[str, object]) -> None:
                if message.get("type") == "transcript" and not message.get("partial"):
                    host.note_transcript(str(message.get("role", "tutor")), str(message.get("text", "")))
                await socket.send_json(message)

            try:
                await talk.start()
                pump = asyncio.create_task(talk.pump(emit))
                print("schoolbook: OpenAI Realtime session is live.", file=sys.stderr)
            except Exception as exc:
                print(f"schoolbook: OpenAI Realtime failed ({exc}); retrying.", file=sys.stderr)
                try:
                    await talk.start()
                    pump = asyncio.create_task(talk.pump(emit))
                    print("schoolbook: OpenAI Realtime session is live.", file=sys.stderr)
                except Exception as retry_exc:
                    talk = None
                    print(f"schoolbook: OpenAI Realtime still down ({retry_exc}).", file=sys.stderr)
        try:
            while True:
                try:
                    incoming = parse_client_message(await socket.receive_json())
                except WebSocketDisconnect:
                    break
                if incoming.type == "ping":
                    await socket.send_json({"type": "pong"})
                elif incoming.type == "dev_text" and host.dev_text:
                    outcome = host.runtime.child_turn(host.ensure_live(), incoming.text)
                    for message in _ws_messages(outcome, incoming.turn_id):
                        await socket.send_json(message)
                elif incoming.type == "talk_start":
                    if talk is not None:
                        for message in await talk.reset_listen():
                            await socket.send_json(message)
                    elif host.voice != "realtime":
                        host.begin_talk(incoming.turn_id)
                        await socket.send_json({"type": "state", "name": "listening", "detail": ""})
                elif incoming.type == "audio_frame":
                    if talk is not None:
                        pcm = base64.b64decode(incoming.pcm_b64)
                        await talk.append_pcm16(pcm, incoming.sample_rate)
                    elif host.voice != "realtime":
                        host.add_audio(incoming.turn_id, incoming.pcm_b64)
                elif incoming.type == "talk_end":
                    if talk is not None or host.voice == "realtime":
                        continue
                    turn_id = incoming.turn_id

                    async def emit_turn(done_id: str = turn_id) -> None:
                        messages = await asyncio.to_thread(host.finish_talk, done_id)
                        for message in messages:
                            if done_id in host.cancelled_turns:
                                break
                            await socket.send_json(message)

                    asyncio.create_task(emit_turn())
                elif incoming.type == "choice":
                    outcome = host.runtime.child_turn(host.ensure_live(), f"I choose {incoming.option_id}")
                    for message in _ws_messages(outcome, incoming.turn_id):
                        await socket.send_json(message)
                elif incoming.type == "home":
                    live = host.ensure_live()
                    live.screen = "home"
                    live.playing_video = None
                    await socket.send_json({"type": "state", "name": "home", "detail": ""})
                elif incoming.type == "unlock_gesture":
                    await socket.send_json({"type": "state", "name": "parent_unlock", "detail": ""})
                elif incoming.type == "video_ui":
                    live = host.ensure_live()
                    if incoming.action == "done":
                        live.playing_video = None
                        live.screen = "home"
                    if talk is not None and incoming.action == "pause":
                        await talk.add_system_note(paused_video_note())
                    await socket.send_json(
                        {
                            "type": "video",
                            "action": "stop" if incoming.action == "done" else incoming.action,
                            "video_id": "",
                            "start_s": None,
                            "end_s": None,
                            "at_s": None,
                        }
                    )
        finally:
            if pump is not None:
                pump.cancel()
            if talk is not None:
                await talk.close()

    return app


def console_app(host: Host) -> FastAPI:
    app = FastAPI(title="Schoolbook console")

    def authorized(request: Request) -> bool:
        if not host.lan_enabled and not _local_only(request):
            return False
        cookie = request.cookies.get("schoolbook_session", "")
        now = time.time()
        if host.parent_locked:
            return False
        if not _valid(host.session_secret, cookie, now):
            return False
        if host.parent_seen_at and now - host.parent_seen_at > host.idle_lock_s:
            host.parent_locked = True
            return False
        host.parent_seen_at = now
        return True

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[StarletteResponse]]
    ) -> StarletteResponse:
        if request.url.path == "/api/login" or not request.url.path.startswith("/api/"):
            return await call_next(request)
        if not authorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    @app.post("/api/login")
    def login(body: dict[str, str]) -> JSONResponse:
        ok, detail = host.login(body.get("password", ""), time.time())
        if not ok:
            return JSONResponse({"error": detail}, status_code=401)
        payload = JSONResponse({"ok": True})
        payload.set_cookie("schoolbook_session", detail, httponly=True, samesite="strict")
        return payload

    @app.get("/api/today")
    def today() -> dict[str, object]:
        live = host.live
        flags = _flags(host)
        latest = _sessions(host)
        minutes = 0.0
        if latest:
            started = latest[-1].started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            if latest[-1].ended_at is None:
                minutes = (datetime.now(UTC) - started).total_seconds() / 60
        calls = host.runtime.store.get_setting("model_calls", 0)
        alert = host.runtime.store.get_setting("spend_alert_cents", 0)
        return {
            "in_session": live is not None,
            "paused": bool(live and live.paused),
            "screen": live.screen if live else "idle",
            "minutes": round(minutes, 1),
            "open_flags": [
                {"id": row.id, "reason": row.reason, "severity": row.severity, "excerpt": row.excerpt}
                for row in flags
                if row.resolved_at is None
            ][:5],
            "latest_summary": latest[-1].parent_summary if latest else "",
            "model_calls": calls if isinstance(calls, int) else 0,
            "spend_alert_cents": alert if isinstance(alert, int) else 0,
        }

    @app.get("/api/sessions")
    def sessions() -> list[dict[str, object]]:
        rows = _sessions(host)
        return [
            {"id": row.id, "started_at": row.started_at.isoformat(), "summary": row.parent_summary}
            for row in rows
        ]

    @app.get("/api/sessions/{session_id}")
    def session_detail(session_id: str) -> dict[str, object]:
        with host.runtime.store.session() as db:
            turns = list(db.scalars(select(Turn).where(Turn.session_id == session_id)))
            calls: list[ToolCall] = []
            for turn in turns:
                calls.extend(db.scalars(select(ToolCall).where(ToolCall.turn_id == turn.id)))
        return {
            "turns": [{"role": turn.role, "text": turn.text} for turn in turns],
            "tool_calls": [{"tool": call.tool, "allowed": bool(call.allowed)} for call in calls],
        }

    @app.get("/api/progress")
    def progress() -> dict[str, object]:
        with host.runtime.store.session() as db:
            skills = list(db.scalars(select(Skill)))
            states = list(db.scalars(select(SkillState).where(SkillState.learner_id == host.learner_id)))
        by_id = {row.skill_id: row.state for row in states}
        return {
            "skills": [
                {"id": skill.id, "title": skill.title, "state": by_id.get(skill.id, "not_seen")}
                for skill in skills
            ]
        }

    @app.get("/api/memory")
    def memory() -> dict[str, object]:
        with host.runtime.store.session() as db:
            notes = list(db.scalars(select(Note).where(Note.learner_id == host.learner_id)))
            interests = list(db.scalars(select(Interest).where(Interest.learner_id == host.learner_id)))
            observations = list(
                db.scalars(select(Observation).where(Observation.learner_id == host.learner_id))
            )
        return {
            "notes": [{"id": note.id, "kind": note.kind, "text": note.text} for note in notes],
            "interests": [{"topic": row.topic, "strength": row.strength} for row in interests],
            "observations": [
                {"id": row.id, "skill_id": row.skill_id, "outcome": row.outcome} for row in observations
            ],
        }

    @app.post("/api/memory/forget")
    def forget(body: dict[str, str]) -> dict[str, bool]:
        host.runtime.store.forget(body["kind"], host.learner_id, body["target"])
        return {"ok": True}

    @app.get("/api/library/videos")
    def videos() -> list[dict[str, object]]:
        with host.runtime.store.session() as db:
            rows = list(db.scalars(select(Video)))
        return [
            {
                "id": row.id,
                "title": row.title,
                "verdict": row.verdict,
                "reasons": row.verdict_reasons,
                "level": row.est_level,
                "channel_id": row.channel_id,
            }
            for row in rows
        ]

    @app.post("/api/library/videos/{video_id}/block")
    def block_video(video_id: str) -> dict[str, bool]:
        host.runtime.store.block_video(video_id)
        return {"ok": True}

    @app.post("/api/library/channels/{channel_id}/block")
    def block_channel(channel_id: str) -> dict[str, bool]:
        host.runtime.store.block_channel(channel_id)
        return {"ok": True}

    @app.get("/api/library/images")
    def images() -> list[dict[str, str]]:
        with host.runtime.store.session() as db:
            rows = list(db.scalars(select(ImageRow)))
        return [{"id": row.id, "title": row.title, "license": row.license} for row in rows]

    @app.get("/api/requests")
    def requests() -> list[dict[str, str]]:
        with host.runtime.store.session() as db:
            rows = list(db.scalars(select(ContentRequest)))
        return [
            {"id": row.id, "kind": row.kind, "description": row.description, "status": row.status}
            for row in rows
        ]

    @app.get("/api/apps")
    def apps() -> list[dict[str, object]]:
        disabled = host.runtime.store.get_setting("disabled_apps", [])
        disabled_ids = set(disabled) if isinstance(disabled, list) else set()
        return [
            {
                "id": app_id,
                "name": manifest.name,
                "enabled": app_id not in disabled_ids,
                "activities": [item.id for item in manifest.activities],
            }
            for app_id, manifest in host.runtime.apps.items()
        ]

    @app.post("/api/apps/{app_id}/disable")
    def disable_app(app_id: str) -> dict[str, bool]:
        disabled = host.runtime.store.get_setting("disabled_apps", [])
        ids = set(disabled) if isinstance(disabled, list) else set()
        ids.add(app_id)
        host.runtime.store.put_setting("disabled_apps", sorted(ids))
        return {"ok": True}

    @app.post("/api/session/pause")
    def pause() -> dict[str, bool]:
        live = host.ensure_live()
        live.paused = True
        host.runtime.store.set_paused(live.session_id, True)
        return {"ok": True}

    @app.post("/api/session/end")
    def end() -> dict[str, bool]:
        live = host.ensure_live()
        host.runtime.end_from_parent(live)
        host.live = None
        host.request_kiosk_end()
        return {"ok": True}

    @app.get("/api/learner")
    def learner() -> dict[str, object]:
        row = host.runtime.store.learner(host.learner_id)
        if row is None:
            return {}
        return {
            "first_name": row.first_name,
            "birth_year": row.birth_year,
            "age_profile": row.age_profile,
            "avatar": row.avatar,
            "voice": row.voice,
            "talk_mode": row.talk_mode,
        }

    @app.get("/api/settings")
    def settings() -> dict[str, object]:
        return {
            "model": host.runtime.model,
            "lan": host.lan_enabled,
            "anthropic_api_key": "",
            "keys_are_write_only": True,
        }

    @app.get("/api/export")
    def export() -> dict[str, str]:
        return {"markdown": host.runtime.store.export_markdown(host.learner_id)}

    @app.post("/api/memory/notes")
    def add_note(body: dict[str, str]) -> dict[str, str]:
        note_id = host.runtime.store.add_note(
            host.learner_id, body.get("kind", "house"), body.get("text", ""), None
        )
        return {"id": note_id}

    @app.post("/api/library/videos/{video_id}/unblock")
    def unblock_video(video_id: str) -> dict[str, bool]:
        host.runtime.store.unblock_video(video_id)
        return {"ok": True}

    @app.post("/api/library/channels/{channel_id}/unblock")
    def unblock_channel(channel_id: str) -> dict[str, bool]:
        host.runtime.store.unblock_channel(channel_id)
        return {"ok": True}

    @app.post("/api/library/images")
    def add_image(body: dict[str, str]) -> dict[str, bool]:
        image_id = body.get("id", "")
        if not image_id or "/" in image_id or ".." in image_id:
            return {"ok": False}
        directory = host.data_dir or Path("images")
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{image_id}.svg"
        target.write_text(body.get("svg", ""), encoding="utf-8")
        host.runtime.store.add_image(
            image_id, str(target), body.get("title", image_id), body.get("license", ""), body.get("tags", "")
        )
        return {"ok": True}

    @app.post("/api/requests/{request_id}")
    def update_request(request_id: str, body: dict[str, str]) -> dict[str, bool]:
        host.runtime.store.set_request_status(request_id, body.get("status", "pending"))
        return {"ok": True}

    @app.post("/api/apps/{app_id}/enable")
    def enable_app(app_id: str) -> dict[str, bool]:
        disabled = host.runtime.store.get_setting("disabled_apps", [])
        ids = set(disabled) if isinstance(disabled, list) else set()
        ids.discard(app_id)
        host.runtime.store.put_setting("disabled_apps", sorted(str(item) for item in ids))
        return {"ok": True}

    @app.put("/api/apps/{app_id}")
    def app_cap(app_id: str, body: dict[str, object]) -> dict[str, bool]:
        caps = host.runtime.store.get_setting("app_caps", {})
        mapping = dict(caps) if isinstance(caps, dict) else {}
        if "cap_minutes" in body:
            mapping[app_id] = body["cap_minutes"]
            host.runtime.store.put_setting("app_caps", mapping)
        if body.get("enabled") is False:
            disable_ids = host.runtime.store.get_setting("disabled_apps", [])
            ids = set(disable_ids) if isinstance(disable_ids, list) else set()
            ids.add(app_id)
            host.runtime.store.put_setting("disabled_apps", sorted(str(item) for item in ids))
        return {"ok": True}

    @app.patch("/api/learner")
    def update_learner(body: dict[str, object]) -> dict[str, bool]:
        current = host.runtime.store.learner(host.learner_id)
        if current is None:
            return {"ok": False}
        first_name = body.get("first_name", current.first_name)
        birth_year = body.get("birth_year", current.birth_year)
        host.runtime.store.upsert_learner(
            learner_id=host.learner_id,
            first_name=str(first_name),
            birth_year=int(str(birth_year)),
            age_profile=str(body.get("age_profile", current.age_profile)),
            avatar=str(body.get("avatar", current.avatar)),
            voice=str(body.get("voice", current.voice)),
            talk_mode=str(body.get("talk_mode", current.talk_mode)),
        )
        return {"ok": True}

    @app.put("/api/settings")
    def update_settings(body: dict[str, object]) -> dict[str, object]:
        if "lan" in body:
            host.lan_enabled = bool(body["lan"])
        if isinstance(body.get("model"), str):
            host.runtime.model = str(body["model"])
        if "break_suggestions" in body:
            host.runtime.store.put_setting("break_suggestions", body["break_suggestions"])
        if "spend_alert_cents" in body:
            host.runtime.store.put_setting("spend_alert_cents", body["spend_alert_cents"])
        updates: dict[str, str] = {}
        for key, env_name in (
            ("anthropic_api_key", "ANTHROPIC_API_KEY"),
            ("youtube_api_key", "YOUTUBE_API_KEY"),
        ):
            value = body.get(key)
            if isinstance(value, str) and value:
                updates[env_name] = value
        password = body.get("parent_password")
        if isinstance(password, str) and password:
            host.password_hash = hash_password(password)
            updates["PARENT_PASSWORD_HASH"] = host.password_hash
        if updates and host.secrets_path is not None:
            upsert_secrets(host.secrets_path, updates)
        return {"ok": True, "anthropic_api_key": "", "youtube_api_key": ""}

    @app.post("/api/session/relock")
    def relock() -> dict[str, bool]:
        host.parent_locked = True
        host.parent_seen_at = 0.0
        return {"ok": True}

    @app.post("/api/session/logout")
    def logout() -> dict[str, str]:
        host.parent_seen_at = 0.0
        return {"action": "greeter"}

    @app.post("/api/session/shutdown")
    def shutdown() -> dict[str, str]:
        host.runtime.store.put_setting("shutdown_requested", True, actor="parent")
        return {"action": "shutdown"}

    @app.post("/api/flags/{flag_id}/resolve")
    def resolve_flag(flag_id: str) -> dict[str, bool]:
        host.runtime.store.resolve_flag(flag_id)
        return {"ok": True}

    @app.get("/api/backup")
    def backup() -> dict[str, object]:
        if not host.backup_repository or host.data_dir is None:
            return {"configured": False, "command": []}
        command = restic_backup_command(host.backup_repository, [host.data_dir])
        return {"configured": True, "command": command}

    @app.post("/api/learner/delete")
    def delete_learner() -> dict[str, bool]:
        host.runtime.store.delete_learner_data(host.learner_id)
        host.live = None
        return {"ok": True}

    return app


def _flags(host: Host) -> list[Flag]:
    with host.runtime.store.session() as db:
        return list(db.scalars(select(Flag)))


def _sessions(host: Host) -> list[SessionRow]:
    with host.runtime.store.session() as db:
        return list(db.scalars(select(SessionRow)))


def _outcome_payload(outcome: TurnOutcome) -> dict[str, object]:
    return {
        "sentences": outcome.sentences,
        "tools": [record.name for record in outcome.tool_calls if record.allowed],
        "flagged": outcome.flagged,
    }


def _ws_messages(outcome: TurnOutcome, turn_id: str) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    for record in outcome.tool_calls:
        if not record.allowed:
            continue
        if record.name == "show_board":
            elements = record.arguments.get("elements", [])
            messages.append({"type": "board", "turn_id": turn_id, "elements": elements})
        if record.name == "ask_choice":
            messages.append(
                {
                    "type": "choices",
                    "turn_id": turn_id,
                    "prompt": record.arguments.get("prompt", ""),
                    "options": record.arguments.get("options", []),
                }
            )
        if record.name == "play_video":
            messages.append(
                {
                    "type": "video",
                    "action": "play",
                    "video_id": record.arguments.get("video_id", ""),
                    "start_s": record.arguments.get("start"),
                    "end_s": record.arguments.get("end"),
                    "at_s": None,
                }
            )
    messages.append(
        {
            "type": "transcript",
            "turn_id": turn_id,
            "role": "tutor",
            "text": " ".join(outcome.sentences),
            "partial": False,
        }
    )
    return messages
