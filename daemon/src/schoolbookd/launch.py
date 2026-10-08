# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""One command to start the daemon and a cage kiosk session."""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

from schoolbookd.config import check_config, load_config
from schoolbookd.policy.unlock import hash_password


class LaunchError(RuntimeError):
    pass


@dataclass(frozen=True)
class KioskPlan:
    daemon_cmd: list[str]
    cage_cmd: list[str]


def require_ui(share: Path) -> None:
    if not (share / "ui" / "dist" / "index.html").is_file():
        raise LaunchError("child UI is not built; missing ui/dist. Run npm ci && npm run build in ui/")
    if not (share / "console" / "dist" / "index.html").is_file():
        raise LaunchError("parent console is not built; run npm ci && npm run build in console/")


def find_share() -> Path:
    repo = Path(__file__).resolve().parents[3]
    if (repo / "prompts" / "core.md").is_file():
        return repo
    cwd = Path.cwd()
    if (cwd / "prompts" / "core.md").is_file():
        return cwd
    raise LaunchError("cannot find Schoolbook share dir (prompts/core.md)")


def prepare_runtime(root: Path, share: Path, parent_password: str) -> Path:
    if not parent_password:
        raise LaunchError("parent password is required to create a runtime")
    etc = root / "etc"
    data = root / "data"
    apps = etc / "apps.d"
    apps.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    manifests = list((share / "apps.d").glob("*.yaml"))
    if not manifests:
        raise LaunchError(f"no app manifests in {share / 'apps.d'}")
    for manifest in manifests:
        shutil.copy(manifest, apps / manifest.name)
    shutil.copy(share / "packaging" / "output-check.txt", etc / "output-check.txt")
    learner = etc / "learner.yaml"
    if not learner.is_file():
        learner.write_text(
            "id: kid\nfirst_name: Arum\nbirth_year: 2020\ntalk_mode: handsfree\n",
            encoding="utf-8",
        )
    upgrade_default_learner(learner)
    secrets_file = etc / "secrets.env"
    secret_lines = [
        f"PARENT_PASSWORD_HASH={hash_password(parent_password)}",
        f"CONSOLE_SESSION_SECRET={secrets.token_urlsafe(32)}",
    ]
    for env_name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "YOUTUBE_API_KEY"):
        value = os.environ.get(env_name, "")
        if value:
            secret_lines.append(f"{env_name}={value}")
    secrets_file.write_text("\n".join(secret_lines) + "\n", encoding="utf-8")
    secrets_file.chmod(0o600)
    llm = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "fake"
    tts = "espeak" if shutil.which("espeak-ng") else "piper"
    voice = "realtime" if os.environ.get("OPENAI_API_KEY") else "pipeline"
    config = root / "schoolbook.yaml"
    config.write_text(
        "\n".join(
            [
                f"data_dir: {data.resolve()}",
                f"share_dir: {share.resolve()}",
                f"etc_dir: {etc.resolve()}",
                "dev_text_input: true",
                "providers:",
                f"  llm: {llm}",
                "  stt: whisper",
                f"  tts: {tts}",
                f"  voice: {voice}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def upgrade_default_learner(path: Path) -> None:
    """Rename the shipped default first name when it is still the old placeholder."""
    if not path.is_file():
        return
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return
    if raw.get("id") != "kid" or raw.get("first_name") != "Sam":
        return
    raw["first_name"] = "Arum"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def should_use_cage(base: dict[str, str] | None = None) -> bool:
    """Cage is the TTY session compositor. Nested on X11/Wayland desktops is often broken."""
    env = base if base is not None else os.environ
    if env.get("SCHOOLBOOK_FORCE_CAGE") == "1":
        return True
    if env.get("SCHOOLBOOK_NO_CAGE") == "1":
        return False
    session = env.get("XDG_SESSION_TYPE", "")
    if session in {"x11", "wayland", "mir"}:
        return False
    return not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))


def cage_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base if base is not None else os.environ)
    wayland = env.get("WAYLAND_DISPLAY", "")
    runtime = Path(env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    socket_path = Path(wayland) if wayland and Path(wayland).is_absolute() else runtime / wayland
    socket = socket_path if wayland else None
    if wayland and socket is not None and socket.exists():
        env["WLR_BACKENDS"] = "wayland"
    elif env.get("DISPLAY"):
        env["WLR_BACKENDS"] = "x11"
    return env


def kiosk_command(
    *,
    session: str,
    url: str,
    data_dir: Path,
    cage: str | None,
) -> list[str]:
    inner = [session, "kiosk", "--url", url, "--data-dir", str(data_dir)]
    if cage is None:
        return inner
    return [cage, "--", *inner]


def build_plan(
    *,
    config_path: Path,
    url: str,
    data_dir: Path,
    python: str,
    session: str,
    cage: str | None,
) -> KioskPlan:
    return KioskPlan(
        daemon_cmd=[python, "-m", "schoolbookd", "--config", str(config_path), "serve"],
        cage_cmd=kiosk_command(session=session, url=url, data_dir=data_dir, cage=cage),
    )


def wait_health(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    raise LaunchError(f"daemon did not become ready at {url}")


def load_env_file(path: Path) -> None:
    """Load KEY=value lines without overwriting keys already in the environment."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def _upgrade_voice_providers(config_path: Path) -> None:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return
    providers = raw.setdefault("providers", {})
    if not isinstance(providers, dict):
        return
    changed = False
    if providers.get("stt", "fake") == "fake":
        providers["stt"] = "whisper"
        changed = True
    if providers.get("tts", "fake") == "fake":
        providers["tts"] = "espeak" if shutil.which("espeak-ng") else "piper"
        changed = True
    if providers.get("llm", "fake") == "fake" and os.environ.get("ANTHROPIC_API_KEY"):
        providers["llm"] = "anthropic"
        changed = True
    if providers.get("voice", "pipeline") != "realtime" and os.environ.get("OPENAI_API_KEY"):
        providers["voice"] = "realtime"
        changed = True
    if changed:
        config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def _which(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise LaunchError(f"{name} is not installed")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="schoolbook",
        description="Start Schoolbook locked into a cage kiosk until a parent ends the session.",
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--share-dir", type=Path)
    parser.add_argument("--parent-password", default="")
    parser.add_argument("--dev", action="store_true", help="show the developer text box")
    args = parser.parse_args(argv)
    try:
        share = args.share_dir or find_share()
        load_env_file(share / ".env")
        load_env_file(Path.home() / ".config" / "schoolbook" / "env")
        require_ui(share)
        session = _which("schoolbook-session")
        cage_bin = shutil.which("cage")
        cage = cage_bin if cage_bin and should_use_cage() else None
        if cage_bin and cage is None:
            print(
                "schoolbook: launching Chromium kiosk on this desktop. "
                "Cage is reserved for a TTY or SCHOOLBOOK_FORCE_CAGE=1.",
                file=sys.stderr,
            )
        elif cage is None:
            print(
                "schoolbook: cage is not installed; launching Chromium kiosk without a compositor.",
                file=sys.stderr,
            )
        runtime = args.runtime_dir or Path.home() / ".local/share/schoolbook"
        if args.config is not None:
            config_path = args.config
            upgrade_default_learner(config_path.parent / "etc" / "learner.yaml")
        else:
            secrets_file = runtime / "etc" / "secrets.env"
            config_path = runtime / "schoolbook.yaml"
            if not (secrets_file.is_file() and config_path.is_file() and not args.parent_password):
                if not args.parent_password:
                    raise LaunchError("pass --parent-password on the first run")
                config_path = prepare_runtime(runtime, share, parent_password=args.parent_password)
            else:
                _upgrade_voice_providers(config_path)
                upgrade_default_learner(runtime / "etc" / "learner.yaml")
        config = load_config(config_path)
        errors = check_config(config)
        if errors:
            raise LaunchError("; ".join(errors))
        query = "?dev=1" if args.dev else ""
        url = f"http://127.0.0.1:{config.ports.child}/{query}"
        plan = build_plan(
            config_path=config_path,
            url=url,
            data_dir=config.data_dir,
            python=sys.executable,
            session=session,
            cage=cage,
        )
        env = cage_env()
        if cage is not None and env.get("WLR_BACKENDS") in {"wayland", "x11"}:
            print(
                "schoolbook: cage is nested on this desktop; Super or Alt-Tab may still reach other apps. "
                "Run from a TTY for a full lock.",
                file=sys.stderr,
            )
        print(
            "schoolbook: starting kiosk. Hold the top-right corner for 5 seconds, then End session to leave.",
            file=sys.stderr,
        )
        daemon = subprocess.Popen(plan.daemon_cmd)
        try:
            wait_health(f"http://127.0.0.1:{config.ports.child}/health")
            completed = subprocess.run(plan.cage_cmd, env=env, check=False)
            if completed.returncode != 0 and cage is not None:
                print(
                    "schoolbook: cage failed to start; launching Chromium kiosk on this desktop.",
                    file=sys.stderr,
                )
                completed = subprocess.run(
                    kiosk_command(session=session, url=url, data_dir=config.data_dir, cage=None),
                    env=env,
                    check=False,
                )
        finally:
            daemon.terminate()
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()
        return completed.returncode
    except LaunchError as exc:
        print(f"schoolbook: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
