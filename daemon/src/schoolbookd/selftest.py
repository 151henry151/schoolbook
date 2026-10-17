# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Checks the daemon can open its database and speak a sample."""

from __future__ import annotations

from schoolbookd.bootstrap import build_host
from schoolbookd.config import SchoolbookConfig, Secrets


def run_self_test(config: SchoolbookConfig, secrets: Secrets) -> int:
    host = build_host(config, secrets)
    sample = host.runtime.tts.synthesize("Hello from Schoolbook.")
    if not sample:
        print("schoolbookd: TTS sample was empty")
        return 1
    print(f"schoolbookd: database {config.database_path}")
    print(f"schoolbookd: learner {host.learner_id}")
    print(f"schoolbookd: tts bytes {len(sample)}")
    if config.providers.llm != "anthropic":
        print("schoolbookd: Claude call skipped (provider is not anthropic)")
    if not secrets.youtube_api_key:
        print("schoolbookd: YouTube search skipped (no API key)")
    print("schoolbookd: microphone check skipped (no audio device required in this environment)")
    print("schoolbookd: self-test ok")
    return 0
