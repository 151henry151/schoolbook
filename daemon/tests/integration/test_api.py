# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

from fastapi.testclient import TestClient

from schoolbookd.api import Host, child_app, console_app
from schoolbookd.content.apps import Activity, AppManifest
from schoolbookd.db.engine import make_engine, migrate, session_factory
from schoolbookd.db.models import Skill
from schoolbookd.db.store import Store
from schoolbookd.policy.output_check import OutputCheck
from schoolbookd.policy.unlock import hash_password
from schoolbookd.providers.base import FakeLLM, FakeTTS, LLMResponse, ToolUse
from schoolbookd.runtime import Runtime
from schoolbookd.tutor.prompts import AgeProfile


def _host(tmp_path: Path) -> Host:
    engine = make_engine(tmp_path / "schoolbook.db")
    migrate(engine)
    store = Store(session_factory(engine))
    store.upsert_learner(learner_id="kid", first_name="Sam", birth_year=2020)
    store.replace_skills([Skill(id="math.counting.to20", title="Count to 20", kid_description="Count")])
    runtime = Runtime(
        store=store,
        llm=FakeLLM(
            [
                LLMResponse(
                    text="Sharks are fish. Want to count?",
                    tool_calls=[
                        ToolUse(
                            "show_board",
                            {"elements": [{"type": "big_text", "text": "shark", "highlights": []}]},
                        )
                    ],
                )
            ]
        ),
        tts=FakeTTS(),
        output_check=OutputCheck([]),
        apps={
            "gcompris": AppManifest(
                id="gcompris",
                name="GCompris",
                exec=["gcompris-qt"],
                activities=[Activity(id="enumerate", title="Count")],
            )
        },
        age_profile=AgeProfile(id="age-6"),
        core_prompt="computer helper",
        summary=FakeLLM([LLMResponse(text="Talked about sharks.")]),
    )
    return Host(
        runtime=runtime,
        learner_id="kid",
        token="boot-token",
        password_hash=hash_password("parent-secret"),
        session_secret="cookie-secret",
        dev_text=True,
    )


def test_dev_turn_and_console_lockout(tmp_path: Path) -> None:
    host = _host(tmp_path)
    child = TestClient(child_app(host))
    denied = child.post("/dev/turn", json={"text": "hi"})
    assert denied.status_code == 401
    ok = child.post(
        "/dev/turn",
        json={"text": "Tell me about sharks"},
        headers={"x-schoolbook-token": "boot-token"},
    )
    assert ok.status_code == 200
    assert "Sharks" in ok.json()["sentences"][0]
    assert ok.json()["tools"] == ["show_board"]

    console = TestClient(console_app(host))
    assert console.get("/api/today").status_code == 401
    for _ in range(5):
        assert console.post("/api/login", json={"password": "nope"}).status_code == 401
    locked = console.post("/api/login", json={"password": "parent-secret"})
    assert locked.status_code == 401
    assert locked.json()["error"] == "locked"


def test_parent_login_lists_the_session(tmp_path: Path) -> None:
    host = _host(tmp_path)
    child = TestClient(child_app(host))
    child.post(
        "/dev/turn",
        json={"text": "sharks"},
        headers={"x-schoolbook-token": "boot-token"},
    )
    console = TestClient(console_app(host))
    logged_in = console.post("/api/login", json={"password": "parent-secret"})
    assert logged_in.status_code == 200
    today = console.get("/api/today")
    assert today.json()["in_session"] is True
    progress = console.get("/api/progress")
    assert progress.json()["skills"][0]["id"] == "math.counting.to20"
    console.post("/api/library/channels/bad-channel/block")
    assert "bad-channel" in host.runtime.store.blocked_channels()
    exported = console.get("/api/export")
    assert "Sam" in exported.json()["markdown"]


def test_talk_start_cancels_the_speaking_turn(tmp_path: Path) -> None:
    host = _host(tmp_path)
    host.speaking_turn = "old"
    host.begin_talk("new")
    assert "old" in host.cancelled_turns
    assert host.speaking_turn is None


def test_finish_talk_returns_to_listening(tmp_path: Path) -> None:
    host = _host(tmp_path)
    host.begin_talk("t1")
    messages = host.finish_talk("t1")
    assert messages[-1] == {"type": "state", "name": "listening", "detail": ""}


def test_talk_end_without_audio_skips_the_model(tmp_path: Path) -> None:
    host = _host(tmp_path)
    client = TestClient(child_app(host))
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "hello", "protocol_major": 1, "token": "boot-token"})
        assert socket.receive_json()["type"] == "hello_ok"
        socket.send_json({"type": "talk_end", "turn_id": "t1"})
        message = socket.receive_json()
        assert message["type"] == "transcript"
        assert message["text"] == "I didn't catch that."
    assert host.runtime.llm.requests == []


def test_settings_keys_are_write_only_and_idle_relocks(tmp_path: Path) -> None:
    host = _host(tmp_path)
    host.secrets_path = tmp_path / "secrets.env"
    console = TestClient(console_app(host))
    assert console.post("/api/login", json={"password": "parent-secret"}).status_code == 200
    saved = console.put("/api/settings", json={"anthropic_api_key": "sk-test", "lan": True})
    assert saved.json()["anthropic_api_key"] == ""
    assert "sk-test" in (tmp_path / "secrets.env").read_text(encoding="utf-8")
    assert console.get("/api/settings").json()["anthropic_api_key"] == ""
    host.parent_seen_at = 1
    assert console.get("/api/today").status_code == 401


def test_websocket_rejects_the_wrong_protocol_major(tmp_path: Path) -> None:
    host = _host(tmp_path)
    client = TestClient(child_app(host))
    with client.websocket_connect("/ws") as socket:
        socket.send_json({"type": "hello", "protocol_major": 99, "token": "boot-token"})
        message = socket.receive_json()
        assert message["type"] == "error"


def test_parent_end_session_requests_kiosk_exit(tmp_path: Path) -> None:
    host = _host(tmp_path)
    host.data_dir = tmp_path
    console = TestClient(console_app(host))
    assert console.post("/api/login", json={"password": "parent-secret"}).status_code == 200
    assert console.post("/api/session/end").status_code == 200
    assert (tmp_path / "kiosk.end").read_text(encoding="utf-8").strip() == "end"


def test_child_unlock_end_requests_kiosk_exit(tmp_path: Path) -> None:
    host = _host(tmp_path)
    host.data_dir = tmp_path
    child = TestClient(child_app(host))
    ended = child.post(
        "/unlock",
        json={"password": "parent-secret", "action": "end"},
        headers={"x-schoolbook-token": "boot-token"},
    )
    assert ended.status_code == 200
    assert ended.json()["ended"] is True
    assert (tmp_path / "kiosk.end").read_text(encoding="utf-8").strip() == "end"
