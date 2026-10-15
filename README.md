# Schoolbook

Schoolbook is a locked-down Linux learning environment for one child. The machine boots into a kiosk. The child talks with a tutor, sees a full-screen board, watches vetted videos, and can open a short list of educational apps. A parent console on a separate port shows what happened.

Version 0.9.0 is the software described through phase 8 of [docs/design-spec.md](docs/design-spec.md). Version 1.0.0 waits for a real pilot with a parent nearby. `schoolbook` starts a cage kiosk for the current session. It does not replace the machine's login manager; `packaging/install.sh` is the path that boots straight into Schoolbook.

## Layout

- `daemon/` — `schoolbookd`, the tutor, database, and HTTP API
- `session/` — `schoolbook-session`, the allowlisted app launcher
- `protocol/` — shared message models, protocol major 1
- `ui/` — the child's screen
- `console/` — the parent console
- `prompts/`, `profiles/`, `skills/`, `apps.d/` — shipped content
- `packaging/` — installer, greetd, Chromium policy, systemd, polkit

## Develop

```bash
uv sync --frozen
uv run ruff check protocol daemon session
uv run mypy --strict protocol/src daemon/src session/src
uv run pytest --override-ini='addopts='
uv run reuse lint
```

Build the web apps from `ui/` and `console/` with `npm ci`, `npm test`, and `npm run build`. End-to-end tests live in `e2e/` and need those builds plus Chrome:

```bash
cd e2e && npm ci && npx playwright test
```

`packaging/install.sh --dry-run` prints the lockdown steps. Run the script with sudo only on a machine you intend to turn into a kiosk.

## Run the kiosk

Install `cage`, Chromium, and espeak-ng (`sudo apt install cage chromium espeak-ng` on Debian). Build the UIs once, then start everything with one command:

```bash
(cd ui && npm ci && npm run build)
(cd console && npm ci && npm run build)
uv sync --frozen
uv run schoolbook --parent-password 'choose-a-parent-password'
```

That starts the daemon and opens Chromium inside cage. Hold the top-right corner for five seconds, enter the parent password, and choose **End session** to leave. Later runs can omit `--parent-password` if the runtime under `~/.local/share/schoolbook` already exists.

After the avatar tap, the microphone stays on. Speak, pause, and the tutor answers out loud. It does not show written menus. The tutor finishes a sentence before it listens again. When the child asks for a video, the tutor searches YouTube, vets a candidate, and plays it; it does not ask for a video ID. Set `OPENAI_API_KEY` in a gitignored `.env` for live speech-to-speech (OpenAI Realtime). Video search also needs `YOUTUBE_API_KEY`. Claude's consumer voice mode cannot be embedded; typed `--dev` turns can still use `ANTHROPIC_API_KEY`. On an existing desktop, Schoolbook skips cage and opens Chromium `--kiosk` directly; Super or Alt-Tab may still reach other apps. Run from a TTY for a full lock.

`schoolbookd --config` still serves only the HTTP API if you need that without cage.

## CF-30 kiosk controls

In the CF-30's systemd-managed X11/Openbox kiosk, **F11 restarts Schoolbook**, including the tutor backend, browser, audio session, and any open game. The current conversation is interrupted, but the laptop does not reboot and saved learner data remains. The key is handled by Openbox, so it can recover a frozen browser. It requires the root-run `schoolbook-kiosk.service` and `packaging/xinitrc`; it is not a shortcut in ordinary desktop or Cage sessions. An OS or X server freeze still needs separate recovery.

For an existing CF-30 installation, update the application and rebuild `ui/`, including `packaging/openbox/rc.xml`. Install the updated `packaging/systemd/schoolbook-kiosk.service` in `/etc/systemd/system/` and run `systemctl daemon-reload` as root; its ten-second stop timeout bounds recovery from stuck processes. The Openbox binding takes effect on the next kiosk start. Arrange that restart for a break in use; avoid restarting the kiosk while a child is using it.

The main screen shows the laptop's battery percentage at the top left, with a lightning bolt while charging and a red indicator at 20% or below when discharging. It refreshes every 30 seconds and is hidden while a video, song player, or game is open. Machines without readable battery information show no indicator.

Tap the **microphone** to cancel the current speech attempt and start a fresh connection. Tap the **stop sign** to cancel the attempt and immediately silence the tutor; listening stays paused until the microphone is tapped again. A fresh connection clears the live AI conversation context, while saved learner data and transcripts remain. Connection setup and network waits do not block these controls. A disconnected browser can reconnect on the next microphone tap.

For each speech turn, the finalized transcription shown on screen replaces the corresponding audio message in the tutor’s conversation before a reply is requested. This gives the tutor the same words the parent sees, rather than a separate interpretation of the audio. Names, numbers, and meaningful words are preserved. Unrecognized audio is discarded; a transcription failure shows a recoverable microphone error. Spoken replies still use OpenAI Realtime audio.

While a song or video is playing, microphone capture is stopped and the backend ignores speech input, so talking cannot interrupt playback. Pause or close the player to talk to the tutor again.

## Music controls and familiar songs

The child’s song screen has a large **pause/play** button. Pausing allows speech again; resuming stops microphone capture. Closing a song cancels the remaining queue.

Schoolbook records a song after its audio actually starts, once per play (pausing/resuming does not count twice). History is saved per learner in SQLite and survives restarts. Requests such as “I want to hear some music” use `play_music` to shuffle previously heard, still-approved songs and play each once. Naming a song keeps the existing search-and-play behavior. If there is no history yet, the tutor asks which song to play. History begins with this update; old video play counts cannot reliably distinguish songs. Parent blocks are rechecked before each queued track. Migration `0002` adds `song_plays` without changing existing learner records.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
