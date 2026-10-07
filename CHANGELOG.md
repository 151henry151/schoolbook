# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- README describing the planned application
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
