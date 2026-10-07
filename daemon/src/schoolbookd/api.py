# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Child WebSocket and parent console HTTP API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.responses import Response as StarletteResponse

from schoolbook_protocol.messages import parse_client_message
from schoolbook_protocol.version import MAJOR
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
from schoolbookd.policy.unlock import UnlockState, attempt_unlock
from schoolbookd.runtime import LiveState, Runtime
from schoolbookd.tutor.loop import TurnOutcome

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
        return True, _sign(self.session_secret, now + 3600)


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

    @app.post("/dev/turn")
    def dev_turn(body: dict[str, str], request: Request) -> JSONResponse:
        if not host.dev_text:
            return JSONResponse({"error": "dev text is off"}, status_code=404)
        if request.headers.get("x-schoolbook-token") != host.token:
            return JSONResponse({"error": "bad token"}, status_code=401)
        outcome = host.runtime.child_turn(host.ensure_live(), body.get("text", ""))
        return JSONResponse(_outcome_payload(outcome))

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
        await socket.send_json({"type": "hello_ok", "protocol_major": MAJOR, "learner_name": name})
        while True:
            incoming = parse_client_message(await socket.receive_json())
            if incoming.type == "ping":
                await socket.send_json({"type": "pong"})
            elif incoming.type == "dev_text" and host.dev_text:
                outcome = host.runtime.child_turn(host.ensure_live(), incoming.text)
                for message in _ws_messages(outcome, incoming.turn_id):
                    await socket.send_json(message)
            elif incoming.type == "unlock_gesture":
                await socket.send_json({"type": "state", "name": "parent_unlock", "detail": ""})
            elif incoming.type == "video_ui":
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

    return app


def console_app(host: Host) -> FastAPI:
    app = FastAPI(title="Schoolbook console")

    def authorized(request: Request) -> bool:
        if not host.lan_enabled and not _local_only(request):
            return False
        cookie = request.cookies.get("schoolbook_session", "")
        return _valid(host.session_secret, cookie, time.time())

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[StarletteResponse]]
    ) -> StarletteResponse:
        if request.url.path == "/api/login":
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
        return {
            "in_session": live is not None,
            "paused": bool(live and live.paused),
            "screen": live.screen if live else "idle",
            "open_flags": [row.reason for row in flags if row.resolved_at is None][:5],
            "latest_summary": latest[-1].parent_summary if latest else "",
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
    messages: list[dict[str, object]] = [
        {
            "type": "transcript",
            "turn_id": turn_id,
            "role": "tutor",
            "text": " ".join(outcome.sentences),
            "partial": False,
        }
    ]
    for record in outcome.tool_calls:
        if not record.allowed:
            continue
        if record.name == "show_board":
            elements = record.arguments.get("elements", [])
            messages.append({"type": "board", "turn_id": turn_id, "elements": elements})
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
    return messages
