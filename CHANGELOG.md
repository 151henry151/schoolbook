# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- OpenAI Realtime speech-to-speech live talk when `OPENAI_API_KEY` is set
- Connect to the GA Realtime API without the retired beta header
- Keep live replies on OpenAI speech and skip written choice menus for a child who cannot read yet
- Search and vet YouTube videos from live talk, then play only IDs that passed vetting
- Hands-free live talk: the microphone stays open, 1.5s of silence ends a turn, and speech interrupts the tutor
- AudioWorklet capture of 16 kHz PCM, a playback queue that drops cancelled turns, and Chromium mic auto-grant in kiosk
- Whisper STT via faster-whisper and espeak-ng TTS, used by default instead of fake providers
- `schoolbook` command that starts the daemon and a cage Chromium kiosk from one binary
- Launcher loads a gitignored `.env` for API keys without overwriting the process environment
- Kiosk launch falls back to Chromium without cage when the compositor is missing
- Cage uses the X11 backend on Xorg sessions instead of a missing Wayland nest
- Desktop X11/Wayland sessions skip nested cage and start Chromium kiosk directly
- Session-agent `kiosk` mode that launches localhost Chromium `--kiosk` and restarts it after a crash
- Parent End session writes a kiosk exit flag so cage returns to the previous session

### Changed

- Hold the child's next turn until the tutor finishes speaking
- Change the default learner first name from Sam to Arum
- Resume capture audio from the avatar tap, fall back if AudioWorklet fails, and show a microphone error
- End a live turn after 1.5s of mostly-quiet audio and ignore leftover noise while the tutor is thinking
- Detect voice with RMS hysteresis instead of a low peak threshold
- Child unlock dialog sends the boot token and shows an End session action after a correct password
- Chromium policy allowlist includes the parent console on `127.0.0.1:8766`
- Speak about videos in everyday words and do not call them safe or vetted
- Start videos automatically and hide the written play, pause, and done buttons
- Mute the tutor microphone while a video plays, tap the picture to pause or resume, and close it with a red X
- Prefer stretch-level educational videos for ages 10-12 and drop baby-entertainment search hits
- Turn a child's video request into a parent briefing so the tutor picks history or science, not baby TV
- Finish the tutor's spoken reply before a video starts
- Keep the child's words on screen above the tutor reply, with playful type and speaker icons
- Show the child's words as they are spoken and highlight the tutor word that is playing
- Listen again when a video is paused so the child can ask for a different one or change the subject
- Generate an educational picture with OpenAI and show it when the child asks to see something
- Keep YouTube search queries short, retry empty caches, and fall back to an approved video on the same topic
- Keep the microphone closed until tutor audio finishes so the tutor does not answer its own voice
- Ask the child to confirm when a transcript looks garbled instead of guessing
- Answer a question over a paused video, keep the player, and resume or stop after they choose
- Use a bigger cartoon pointer with a white center and a blue outline, and hide it during video until the mouse moves
- Wait longer after the child pauses, drop um and leftover noise, and answer only when a real sentence is there
- Speak unclear words back out loud when a clarification is needed, because the child cannot read
- Steer made-up character and pretend-land talk toward something real the child can learn
- Add a round microphone button that stops the tutor and the child's turn and starts a fresh listen from the click
- Add a stop-sign button that pauses listening until the child taps the microphone again
- Let the child switch the tutor voice by asking to talk to somebody else, or to a boy or girl voice
- Let the child give the tutor a name by voice and have the tutor answer to that name

## [0.9.0] - 2026-10-07

### Added

- README for local development, tests, and the kiosk installer
- Design and implementation specification
- GPL-3.0-or-later license and REUSE metadata
- uv workspace for the protocol, daemon, and session packages
- Shared protocol models for board elements, the child WebSocket, and the session socket
- Config loader that rejects malformed Schoolbook YAML, plus `schoolbookd --check-config`
- Alembic migration for the SQLite tables in the design spec
- Tool policy, parent unlock lockout, and local output check
- Learner-state rules, interest decay, stretch levels, and profile assembly
- YouTube hard filters, vetting stages, app argv builder, and screen-observer hashing
- Tutor loop with fake providers, sentence limits, output checks, and distress flags
- Database store for sessions, skills, interests, notes, videos, and forget
- Runtime that logs a scripted child turn and builds app argv from manifests
- Child WebSocket and parent console HTTP API with login lockout and channel blocks
- Session agent that launches only allowlisted argv and keeps Chromium on localhost
- Anthropic, Piper, whisper.cpp, and YouTube Data API clients behind the provider interfaces
- Age-6 kid-speak scorer for sentence count, one question, and no markdown
- Core charter, age-6 and age-9 profiles, the starter skills tree, and seed app manifests
- Install script, systemd unit, greetd, Chromium policy, polkit, logind, and sysctl lockdown files
- Daemon bootstrap, static file serving, config self-test, and a localhost token for the child UI
- Child UI with a home avatar, board, talk button, and developer text box
- YouTube search cache and vetting that drop blocked channels before the tutor sees them
- Tap-to-talk transcription, sentence audio, write-only settings, image upload, and app time caps
- Optional ntfy alerts, restic backup commands, and a five-minute parent idle relock
- Unix-socket session agent and a two-second browser restart delay
- Child video overlay on the youtube-nocookie embed, a five-second parent hold, and an offline app shelf
- Parent console screens for today, sessions, progress, memory, library, apps, session, learner, and settings
- Playwright coverage for a typed child turn, console login, relock, and password lockout
- GitHub Actions workflow for lint, types, tests, UI builds, and end-to-end tests
- CC0 star image and a NOTICE file for bundled media licenses
