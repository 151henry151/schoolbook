# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Build a runtime from on-disk config, prompts, skills, and apps."""

from __future__ import annotations

import contextlib
import os
import secrets as secrets_mod
import shutil
import subprocess
from pathlib import Path

import yaml
from sqlalchemy import select

from schoolbookd.api import Host
from schoolbookd.config import SchoolbookConfig, Secrets
from schoolbookd.content.apps import load_manifests
from schoolbookd.content.catalog import CharterReviewer, SearchClient, VideoCatalog
from schoolbookd.content.pictures import PictureMaker
from schoolbookd.content.skills import load_skill_rows
from schoolbookd.db.engine import backup_database, make_engine, migrate, session_factory
from schoolbookd.db.models import Learner
from schoolbookd.db.store import Store
from schoolbookd.notify import Notifier
from schoolbookd.overlay import show_close_overlay
from schoolbookd.policy.output_check import OutputCheck
from schoolbookd.providers.base import FakeLLM, FakeSTT, FakeTTS, LLMProvider, STTProvider, TTSProvider
from schoolbookd.runtime import Runtime
from schoolbookd.safety.classifier import KeywordClassifier
from schoolbookd.tutor.prompts import load_age_profile


def build_host(config: SchoolbookConfig, secrets: Secrets) -> Host:
    backup_database(config.database_path, config.backups_dir)
    engine = make_engine(config.database_path)
    migrate(engine)
    store = Store(session_factory(engine))
    store.replace_skills(load_skill_rows(config.skills_file))
    _load_images(store, config.share_dir / "images")
    _ensure_learner(store, config.etc_dir / "learner.yaml")
    learner_id = _first_learner_id(store)
    apps = load_manifests(config.apps_dir)
    profile = load_age_profile(config.profiles_dir / "age-6.yaml")
    token = secrets_mod.token_urlsafe(32)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.images_dir.mkdir(parents=True, exist_ok=True)
    config.token_file.write_text(token + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        config.token_file.chmod(0o640)
    reviewer = CharterReviewer()
    runtime = Runtime(
        store=store,
        llm=_llm(config, secrets),
        tts=_tts(config),
        output_check=OutputCheck.load(config.output_check_file),
        apps=apps,
        age_profile=profile,
        core_prompt=config.core_prompt.read_text(encoding="utf-8"),
        model=config.model if config.providers.llm == "anthropic" else "fake",
        summary=_llm(config, secrets),
        catalog=VideoCatalog(
            store,
            _youtube(secrets),
            reviewer,
            reviewer,
            duration_minutes=_duration(profile.video_duration_minutes),
            language=profile.language,
        ),
        classifier=KeywordClassifier() if config.providers.classifier else None,
        notifier=Notifier(
            config.notifications.ntfy_url,
            config.notifications.ntfy_topic,
            config.notifications.email_to,
        ),
        min_video_pause_s=float(profile.watch_along_pause_min_seconds),
        pictures=_pictures(secrets, config.summary_model),
        images_dir=config.images_dir,
        launcher=_spawn_app,
        killer=_kill_app,
        overlay=show_close_overlay,
    )
    return Host(
        runtime=runtime,
        learner_id=learner_id,
        token=token,
        password_hash=secrets.parent_password_hash,
        session_secret=secrets.console_session_secret or secrets_mod.token_urlsafe(32),
        dev_text=config.dev_text_input,
        lan_enabled=config.lan.enabled,
        stt=make_stt(config),
        secrets_path=config.secrets_file,
        backup_repository=config.backup.restic_repository,
        data_dir=config.data_dir,
        voice=config.providers.voice,
        openai_api_key=secrets.openai_api_key,
    )


def _load_images(store: Store, directory: Path) -> None:
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.svg")):
        store.add_image(path.stem, str(path), path.stem, "CC0-1.0", "shipped")


def _ensure_learner(store: Store, path: Path) -> None:
    if not path.is_file():
        return
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    store.upsert_learner(
        learner_id=str(raw["id"]),
        first_name=str(raw["first_name"]),
        birth_year=int(raw["birth_year"]),
        age_profile=str(raw.get("age_profile", "age-6")),
        avatar=str(raw.get("avatar", "star")),
        voice=str(raw.get("voice", "piper-warm")),
        talk_mode=str(raw.get("talk_mode", "handsfree")),
    )


def _first_learner_id(store: Store) -> str:
    with store.session() as db:
        learner = db.scalars(select(Learner)).first()
    if learner is None:
        raise RuntimeError("no learner configured; add etc/learner.yaml")
    return str(learner.id)


def _llm(config: SchoolbookConfig, secrets: Secrets) -> LLMProvider:
    if config.providers.llm == "anthropic":
        from schoolbookd.providers.anthropic import AnthropicLLM

        return AnthropicLLM(secrets.anthropic_api_key, config.model)
    return FakeLLM([])


def _tts(config: SchoolbookConfig) -> TTSProvider:
    if config.providers.tts == "piper":
        from schoolbookd.providers.piper import PiperTTS

        return PiperTTS()
    if config.providers.tts == "espeak":
        from schoolbookd.providers.espeak import EspeakTTS

        return EspeakTTS()
    return FakeTTS()


def _duration(window: list[int]) -> tuple[int, int]:
    if len(window) != 2:
        return (1, 30)
    return (window[0], window[1])


def _pictures(secrets: Secrets, model: str = "claude-sonnet-5-5") -> PictureMaker | None:
    if secrets.anthropic_api_key:
        from schoolbookd.providers.claude_pictures import ClaudePictures

        return ClaudePictures(secrets.anthropic_api_key, model=model)
    if secrets.openai_api_key:
        from schoolbookd.providers.openai_images import OpenAIImages

        return OpenAIImages(secrets.openai_api_key)
    return None


def _youtube(secrets: Secrets) -> SearchClient | None:
    if not secrets.youtube_api_key:
        return None
    from schoolbookd.providers.youtube import YouTubeClient

    return YouTubeClient(secrets.youtube_api_key)


def _kill_app(pid: int) -> None:
    import signal

    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.kill(pid, signal.SIGTERM)


def _spawn_app(argv: list[str]) -> int:
    command = list(argv)
    if command:
        found = shutil.which(command[0])
        if found:
            command[0] = found
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return int(process.pid)


def make_stt(config: SchoolbookConfig) -> STTProvider:
    if config.providers.stt == "whisper":
        from schoolbookd.providers.whisper import WhisperSTT

        return WhisperSTT()
    return FakeSTT([])
