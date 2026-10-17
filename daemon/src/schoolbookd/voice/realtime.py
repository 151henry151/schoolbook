# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Keep speech connection work cancellable independently of child controls."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

from schoolbookd.providers.openai_realtime import Emit, RealtimeTalk, SpeechUnavailable


class RealtimeSession:
    def __init__(
        self, factory: Callable[[], RealtimeTalk], emit: Emit, invalidate: Callable[[], None]
    ) -> None:
        self.factory = factory
        self.emit = emit
        self.invalidate = invalidate
        self.attempt_id = ""
        self.talk: RealtimeTalk | None = None
        self._generation = 0
        self._task: asyncio.Task[None] | None = None
        self._retired: set[asyncio.Task[None]] = set()
        self._notes: set[asyncio.Task[None]] = set()
        self.media_playing = False
        self._audio: asyncio.Queue[tuple[bytes, int]] = asyncio.Queue(maxsize=1024)

    def reset(self, attempt_id: str, *, listen: bool = True) -> None:
        self._generation += 1
        self.attempt_id = attempt_id
        self.talk = None
        self.invalidate()
        for task in self._notes:
            task.cancel()
        if self._task is not None:
            self._task.cancel()
            self._retired.add(self._task)
            self._task.add_done_callback(self._retired.discard)
        self._task = None
        self._audio = asyncio.Queue(maxsize=1024)
        if listen:
            self._task = asyncio.create_task(self._run(self._generation, attempt_id, self._audio))

    def audio(self, pcm: bytes, rate: int, attempt_id: str) -> None:
        if self.media_playing or self._task is None or self._task.done() or attempt_id != self.attempt_id:
            return
        # Bound buffered audio while connecting; never let network backpressure block Stop.
        if self._audio.full():
            self._audio.get_nowait()
        self._audio.put_nowait((pcm, rate))

    def set_media_playing(self, playing: bool) -> None:
        self.media_playing = playing
        while not self._audio.empty():
            self._audio.get_nowait()
        if self.talk is not None:
            self.talk.input_paused = playing
            self.talk.mapper.drop_input = True

    def note(self, text: str, *, speak: bool = False) -> None:
        talk = self.talk
        if talk is None:
            return

        async def send() -> None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(talk.add_system_note(text, speak=speak), timeout=5)

        task = asyncio.create_task(send())
        self._notes.add(task)
        task.add_done_callback(self._notes.discard)

    async def _run(self, generation: int, attempt_id: str, audio: asyncio.Queue[tuple[bytes, int]]) -> None:
        talk: RealtimeTalk | None = None
        sender: asyncio.Task[None] | None = None

        async def emit(message: dict[str, object]) -> None:
            if generation == self._generation:
                await self.emit({**message, "attempt_id": attempt_id})

        async def send_audio() -> None:
            while True:
                pcm, rate = await audio.get()
                if not self.media_playing and talk is not None:
                    await asyncio.wait_for(talk.append_pcm16(pcm, rate), timeout=5)

        receiver: asyncio.Task[None] | None = None
        try:
            talk = self.factory()
            self.talk = talk
            talk.input_paused = self.media_playing
            await asyncio.wait_for(talk.start(), timeout=10)
            await emit({"type": "state", "name": "listening", "detail": "ready"})
            sender = asyncio.create_task(send_audio())
            receiver = asyncio.create_task(talk.pump(emit))
            done, _pending = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
            raise ConnectionError("speech connection ended")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Log the failure category, never credentials, audio, or provider payloads.
            logging.getLogger(__name__).warning("Speech session failed: %s", type(exc).__name__)
            message = str(exc) if isinstance(exc, SpeechUnavailable) else (
                "Speech connection lost. Tap the microphone to try again."
            )
            await emit(
                {"type": "error", "message": message}
            )
        finally:
            for worker in (sender, receiver):
                if worker is not None:
                    worker.cancel()
            await asyncio.gather(
                *(task for task in (sender, receiver) if task is not None), return_exceptions=True
            )
            if talk is not None:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(talk.close(), timeout=1)
            if generation == self._generation:
                self.talk = None

    async def close(self) -> None:
        self.reset(self.attempt_id, listen=False)
        if self._retired:
            await asyncio.gather(*self._retired, return_exceptions=True)
        if self._notes:
            await asyncio.gather(*self._notes, return_exceptions=True)
