# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

import pytest
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


def test_battery_endpoint_is_uncached_and_local_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("schoolbookd.api.battery_status", lambda: {"percent": 82, "charging": True})
    app = child_app(_host(tmp_path))
    response = TestClient(app).get("/battery")
    assert response.json() == {"percent": 82, "charging": True}
    assert response.headers["cache-control"] == "no-store"
    assert TestClient(app, client=("203.0.113.1", 1234)).get("/battery").status_code == 403


def test_child_controls_replace_stuck_speech_and_stop_without_reopening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    import threading

    from schoolbookd.providers.openai_realtime import RealtimeTalk

    class Talk(RealtimeTalk):
        def __init__(self, stuck: bool) -> None:
            super().__init__("unused", "help", lambda n, a: {})
            self.stuck = stuck
            self.started = threading.Event()
            self.closed = threading.Event()

        async def start(self) -> None:
            self.started.set()
            if self.stuck:
                await asyncio.Event().wait()

        async def pump(self, emit: object) -> None:
            await asyncio.Event().wait()

        async def close(self) -> None:
            self.closed.set()

    talks = [Talk(True), Talk(False)]
    calls: list[Talk] = []

    def factory(host: Host) -> Talk:
        talk = talks[len(calls)]
        calls.append(talk)
        return talk

    monkeypatch.setattr(Host, "make_realtime", factory)
    host = _host(tmp_path)
    host.voice = "realtime"
    host.openai_api_key = "unused"
    with TestClient(child_app(host)).websocket_connect("/ws") as socket:
        socket.send_json({"type": "hello", "protocol_major": 1, "token": "boot-token"})
        assert socket.receive_json()["type"] == "hello_ok"
        socket.send_json({"type": "talk_start", "turn_id": "stuck"})
        assert talks[0].started.wait(1)
        socket.send_json({"type": "ping"})
        assert socket.receive_json()["type"] == "pong"
        socket.send_json({"type": "talk_start", "turn_id": "fresh"})
        assert socket.receive_json() == {
            "type": "state", "name": "listening", "detail": "ready", "attempt_id": "fresh",
        }
        assert talks[0].closed.wait(1)
        socket.send_json({"type": "talk_stop", "turn_id": "stop"})
        socket.send_json({"type": "ping"})
        assert socket.receive_json()["type"] == "pong"
        assert talks[1].closed.wait(1)
        assert len(calls) == 2


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


def test_child_can_load_a_saved_picture(tmp_path: Path) -> None:
    from schoolbookd.content.pictures import TINY_PNG

    host = _host(tmp_path)
    images = tmp_path / "images"
    images.mkdir()
    path = images / "dinosaur.png"
    path.write_bytes(TINY_PNG)
    host.runtime.images_dir = images
    host.runtime.store.add_image("dinosaur", str(path), "dinosaur", "generated", "generated")
    child = TestClient(child_app(host))
    assert child.get("/pictures/nope").status_code == 404
    ok = child.get("/pictures/dinosaur")
    assert ok.status_code == 200
    assert ok.content == TINY_PNG


def test_child_can_stream_a_requested_song(tmp_path: Path) -> None:
    host = _host(tmp_path)

    def fake_song(video_id: str) -> tuple[bytes, str]:
        if video_id != "songid11111":
            raise FileNotFoundError(video_id)
        return b"ID3fake", "audio/mpeg"

    host.song_audio = fake_song
    child = TestClient(child_app(host))
    assert child.get("/songs/https:evil").status_code == 400
    assert child.get("/songs/missingid11").status_code == 404
    ok = child.get("/songs/songid11111")
    assert ok.status_code == 200
    assert ok.content == b"ID3fake"
    assert "audio/mpeg" in ok.headers["content-type"]


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


def test_child_lists_and_joins_wifi(tmp_path: Path) -> None:
    from schoolbookd.net.wifi import Wifi

    def run(argv: list[str], **_kwargs: object) -> object:
        joined = " ".join(argv)
        if "STATE,CONNECTIVITY" in joined:
            return type("Result", (), {"returncode": 0, "stdout": "disconnected:none\n", "stderr": ""})()
        if "NAME,TYPE" in joined:
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        if "wifi list" in joined:
            return type(
                "Result",
                (),
                {"returncode": 0, "stdout": "no:Grandpa:70:WPA2\n", "stderr": ""},
            )()
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    host = _host(tmp_path)
    host.wifi = Wifi(run=run)
    child = TestClient(child_app(host))
    listed = child.get("/wifi")
    assert listed.status_code == 200
    assert listed.json()["networks"][0] == {"ssid": "Grandpa", "signal": 70, "secured": True}
    assert listed.json()["connected"] is False
    denied = child.post("/wifi/connect", json={"ssid": "Grandpa", "password": "house-key"})
    assert denied.status_code == 401
    joined = child.post(
        "/wifi/connect",
        json={"ssid": "Grandpa", "password": "house-key"},
        headers={"x-schoolbook-token": "boot-token"},
    )
    assert joined.status_code == 200
    assert joined.json()["ok"] is True


def test_familiar_song_queue_advances_and_close_cancels_it(tmp_path: Path) -> None:
    host = _host(tmp_path)
    live = host.ensure_live()
    for video_id in ("songid11111", "songid22222"):
        host.runtime.approve_video(video_id, video_id, "music", 1)
        host.runtime.store.record_song_play("kid", video_id)
    first = host.runtime.run_tool(live, "play_music", {})
    with TestClient(child_app(host)).websocket_connect("/ws") as socket:
        socket.send_json({"type": "hello", "protocol_major": 1, "token": "boot-token"})
        assert socket.receive_json()["type"] == "hello_ok"
        socket.send_json({"type": "video_ui", "action": "playing", "video_id": first["playing"]})
        socket.send_json({"type": "video_ui", "action": "ended", "video_id": first["playing"]})
        next_track = socket.receive_json()
        assert next_track["action"] == "play"
        assert next_track["audio_only"] is True
        assert next_track["video_id"] != first["playing"]
        socket.send_json({"type": "video_ui", "action": "ended", "video_id": first["playing"]})
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}  # Old player cannot end the new song.
        socket.send_json({"type": "video_ui", "action": "done", "video_id": next_track["video_id"]})
        assert socket.receive_json()["action"] == "stop"
        assert live.playing_video is None
        assert live.song_queue == []


def test_half_watched_video_event_updates_history_without_stopping_player(tmp_path: Path):
    host = _host(tmp_path)
    runtime = host.runtime
    runtime.approve_video('abcdefghijk', 'Snakes', 'science', 1)
    live = host.ensure_live()
    runtime.run_tool(live, 'play_video', {'video_id': 'abcdefghijk'})
    with TestClient(child_app(host)).websocket_connect('/ws') as socket:
        socket.send_json({'type': 'hello', 'protocol_major': 1, 'token': 'boot-token'})
        socket.receive_json()
        socket.send_json({'type': 'video_ui', 'action': 'watched', 'video_id': 'abcdefghijk',
                          'watched_s': 150, 'duration_s': 300})
        socket.send_json({'type': 'ping'})
        assert socket.receive_json()['type'] == 'pong'
    assert live.playing_video == 'abcdefghijk'
    assert runtime.store.video_history('kid')[0]['watch_count'] == 1


def test_exiting_native_game_notifies_child_without_pressing_schoolbook_close(tmp_path: Path):
    host = _host(tmp_path)
    runtime = host.runtime
    runtime.launcher = lambda argv: 42
    runtime.killer = lambda pid: None
    running = [True]
    runtime.app_running = lambda pid: running[0]
    with TestClient(child_app(host)).websocket_connect('/ws') as socket:
        socket.send_json({'type': 'hello', 'protocol_major': 1, 'token': 'boot-token'})
        socket.receive_json()
        runtime.run_tool(host.ensure_live(), 'launch_app', {'app_id': 'gcompris', 'activity': 'enumerate'})
        running[0] = False
        assert socket.receive_json() == {'type': 'app', 'action': 'stop'}
        assert host.live.screen == 'home'
