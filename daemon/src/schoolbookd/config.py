# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Load and validate /etc/schoolbook/schoolbook.yaml. A bad file refuses to start."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from schoolbook_protocol.version import MAJOR


class ConfigError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class ProvidersConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stt: Literal["fake", "whisper", "deepgram", "assemblyai", "elevenlabs", "openai"] = "fake"
    llm: Literal["fake", "anthropic"] = "fake"
    tts: Literal["fake", "piper", "elevenlabs", "cartesia", "openai"] = "fake"
    classifier: bool = False


class PortsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    child: int = Field(default=8765, ge=1, le=65535)
    console: int = Field(default=8766, ge=1, le=65535)


class LimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_tool_calls_per_turn: int = Field(default=6, ge=1, le=20)
    turn_wall_clock_s: float = Field(default=20, gt=0, le=120)
    login_failures_before_lock: int = Field(default=5, ge=1)
    login_lock_seconds: int = Field(default=300, ge=1)


class LanConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False


class BackupConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    restic_repository: str | None = None


class NotificationsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ntfy_url: str | None = None
    ntfy_topic: str | None = None
    email_to: str | None = None


class SchoolbookConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_dir: Path
    share_dir: Path
    etc_dir: Path
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    model: str = "claude-haiku-5-5"
    summary_model: str = "claude-sonnet-5-5"
    ports: PortsConfig = Field(default_factory=PortsConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    lan: LanConfig = Field(default_factory=LanConfig)
    dev_text_input: bool = False
    backup: BackupConfig = Field(default_factory=BackupConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    store_audio_days: int = Field(default=0, ge=0, le=7)
    observer_speak_when_stuck: bool = True
    protocol_major: int = MAJOR

    @property
    def database_path(self) -> Path:
        return self.data_dir / "schoolbook.db"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def secrets_file(self) -> Path:
        return self.etc_dir / "secrets.env"

    @property
    def apps_dir(self) -> Path:
        return self.etc_dir / "apps.d"

    @property
    def output_check_file(self) -> Path:
        return self.etc_dir / "output-check.txt"

    @property
    def profiles_dir(self) -> Path:
        return self.share_dir / "profiles"

    @property
    def prompts_dir(self) -> Path:
        return self.share_dir / "prompts"

    @property
    def skills_file(self) -> Path:
        return self.share_dir / "skills" / "core.yaml"

    @property
    def token_file(self) -> Path:
        return self.data_dir / "ui.token"

    @property
    def core_prompt(self) -> Path:
        return self.prompts_dir / "core.md"


class Secrets(BaseModel):
    model_config = ConfigDict(extra="ignore")
    anthropic_api_key: str = ""
    youtube_api_key: str = ""
    deepgram_api_key: str = ""
    openai_api_key: str = ""
    elevenlabs_api_key: str = ""
    parent_password_hash: str = ""
    console_session_secret: str = ""


def load_config(path: Path) -> SchoolbookConfig:
    if not path.is_file():
        raise ConfigError([f"config file not found: {path}"])
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError([f"invalid YAML: {exc}"]) from exc
    if not isinstance(raw, dict):
        raise ConfigError(["config must be a mapping"])
    base = path.parent
    for key in ("data_dir", "share_dir", "etc_dir"):
        if key in raw and isinstance(raw[key], str) and not Path(raw[key]).is_absolute():
            raw[key] = str((base / raw[key]).resolve())
    try:
        return SchoolbookConfig.model_validate(raw)
    except ValidationError as exc:
        errors = [f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()]
        raise ConfigError(errors) from exc


def load_secrets(path: Path) -> Secrets:
    values: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip().lower()] = value.strip()
    return Secrets.model_validate(values)


def check_config(config: SchoolbookConfig) -> list[str]:
    """Return human-readable problems. Empty means the daemon may start."""
    errors: list[str] = []
    if config.protocol_major != MAJOR:
        errors.append(f"protocol_major {config.protocol_major} is incompatible with package major {MAJOR}")
    required = [
        config.core_prompt,
        config.skills_file,
        config.output_check_file,
        config.profiles_dir / "age-6.yaml",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing required file: {path}")
    if not config.apps_dir.is_dir():
        errors.append(f"missing apps directory: {config.apps_dir}")
    return errors


def explain_startup(config: SchoolbookConfig, secrets: Secrets) -> list[str]:
    errors = [err for err in check_config(config) if "ANTHROPIC_API_KEY" not in err]
    if config.providers.llm == "anthropic" and not secrets.anthropic_api_key:
        errors.append("providers.llm is anthropic but ANTHROPIC_API_KEY is empty")
    cloud_stt = config.providers.stt in {"deepgram", "assemblyai", "elevenlabs", "openai"}
    if cloud_stt and not _stt_key(config, secrets):
        errors.append(f"providers.stt is {config.providers.stt} but its API key is empty")
    if not secrets.parent_password_hash:
        errors.append("PARENT_PASSWORD_HASH is empty; the parent console cannot be unlocked")
    if not secrets.console_session_secret:
        errors.append("CONSOLE_SESSION_SECRET is empty")
    return errors


def _stt_key(config: SchoolbookConfig, secrets: Secrets) -> str:
    if config.providers.stt == "openai":
        return secrets.openai_api_key
    if config.providers.stt == "elevenlabs":
        return secrets.elevenlabs_api_key
    return secrets.deepgram_api_key
