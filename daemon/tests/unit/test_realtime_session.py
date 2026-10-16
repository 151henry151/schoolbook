# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

import asyncio
import json

from schoolbookd.providers.openai_realtime import RealtimeTalk
from schoolbookd.voice.realtime import RealtimeSession


class Socket:
    def __init__(self, *, handshake: bool = True, block_audio: bool = False) -> None:
        self.incoming: asyncio.Queue[str] = asyncio.Queue()
        self.sent: list[dict[str, object]] = []
        self.closed = False
        self.block_audio = block_audio
        self.sending = asyncio.Event()
        if handshake:
            self.event({"type": "session.created"})

    def event(self, event: dict[str, object]) -> None:
        self.incoming.put_nowait(json.dumps(event))

    async def recv(self) -> str:
        return await self.incoming.get()

    async def send(self, raw: str) -> None:
        value = json.loads(raw)
        if value["type"] == "input_audio_buffer.append" and self.block_audio:
            self.sending.set()
            await asyncio.Event().wait()
        self.sent.append(value)

    async def close(self) -> None:
        self.closed = True


async def settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


def test_reset_replaces_a_stuck_handshake_and_stop_does_not_reopen() -> None:
    async def run() -> None:
        sockets = [Socket(handshake=False), Socket()]
        opened: list[Socket] = []
        emitted: list[dict[str, object]] = []

        async def connect(_key: str) -> Socket:
            socket = sockets[len(opened)]
            opened.append(socket)
            return socket

        async def emit(event: dict[str, object]) -> None:
            emitted.append(event)

        session = RealtimeSession(
            lambda: RealtimeTalk("unused", "help", lambda n, a: {}, connect), emit, lambda: None
        )
        session.reset("old")
        await settle()
        session.reset("fresh")
        session.audio(b"\0\0" * 32, 16000, "old")
        session.audio(b"\0\0" * 32, 16000, "fresh")
        await settle()
        assert sockets[0].closed
        assert any(e.get("detail") == "ready" and e["attempt_id"] == "fresh" for e in emitted)
        assert sum(e["type"] == "input_audio_buffer.append" for e in sockets[1].sent) == 1
        session.reset("stopped", listen=False)
        session.audio(b"\0\0", 16000, "stopped")
        await settle()
        assert sockets[1].closed
        assert len(opened) == 2
        await session.close()

    asyncio.run(run())


def test_stop_interrupts_blocked_audio_send() -> None:
    async def run() -> None:
        socket = Socket(block_audio=True)

        async def connect(_key: str) -> Socket:
            return socket

        async def emit(event: dict[str, object]) -> None:
            pass

        session = RealtimeSession(
            lambda: RealtimeTalk("unused", "help", lambda n, a: {}, connect), emit, lambda: None
        )
        session.reset("one")
        session.audio(b"\0\0", 16000, "one")
        await asyncio.wait_for(socket.sending.wait(), 1)
        await asyncio.wait_for(session.close(), 1)
        assert socket.closed

    asyncio.run(run())


def test_song_playback_drops_queued_audio_and_late_transcriptions() -> None:
    async def run() -> None:
        socket = Socket()
        emitted: list[dict[str, object]] = []

        async def connect(_key: str) -> Socket:
            return socket

        async def emit(event: dict[str, object]) -> None:
            emitted.append(event)

        session = RealtimeSession(
            lambda: RealtimeTalk("unused", "help", lambda n, a: {}, connect), emit, lambda: None
        )
        session.reset("one")
        await settle()
        session.audio(b"\0\0", 16000, "one")
        session.set_media_playing(True)
        session.audio(b"\0\0", 16000, "one")
        socket.event({"type": "input_audio_buffer.speech_started"})
        socket.event(
            {"type": "conversation.item.input_audio_transcription.completed", "transcript": "Stop the song"}
        )
        await settle()
        assert not any(e["type"] in {"input_audio_buffer.append", "response.create"} for e in socket.sent)
        assert not any(e["type"] == "transcript" for e in emitted)
        session.set_media_playing(False)
        session.audio(b"\0\0", 16000, "one")
        await settle()
        assert any(e["type"] == "input_audio_buffer.append" for e in socket.sent)
        await session.close()

    asyncio.run(run())


def test_stop_cancels_album_lookup_without_waiting_for_network_thread():
    import threading

    async def run():
        socket = Socket()
        entered = threading.Event()
        release = threading.Event()
        emitted = []

        async def connect(_key):
            return socket

        async def emit(event):
            emitted.append(event)

        def lookup(name, args):
            entered.set()
            release.wait(timeout=3)
            return {'album_id': 'verified'}

        talk = RealtimeTalk('unused', 'help', lookup, connect)
        await talk.start()
        pump = asyncio.create_task(talk.pump(emit))
        socket.event({'type': 'response.function_call_arguments.done', 'call_id': 'album',
                      'name': 'find_album', 'arguments': '{"title":"Album","artist":"Artist"}'})
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            pump.cancel()
            await asyncio.wait_for(asyncio.gather(pump, return_exceptions=True), 0.5)
            await talk.close()
            assert socket.closed
            assert not any(e.get('type') == 'video' for e in emitted)
        finally:
            release.set()

    asyncio.run(run())
