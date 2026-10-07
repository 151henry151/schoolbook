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
        learner.write_text("id: kid\nfirst_name: Sam\nbirth_year: 2020\n", encoding="utf-8")
    secrets_file = etc / "secrets.env"
    secrets_file.write_text(
        "\n".join(
            [
                f"PARENT_PASSWORD_HASH={hash_password(parent_password)}",
                f"CONSOLE_SESSION_SECRET={secrets.token_urlsafe(32)}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    secrets_file.chmod(0o600)
    config = root / "schoolbook.yaml"
    config.write_text(
        "\n".join(
            [
                f"data_dir: {data.resolve()}",
                f"share_dir: {share.resolve()}",
                f"etc_dir: {etc.resolve()}",
                "dev_text_input: true",
                "providers:",
                "  llm: fake",
                "  stt: fake",
                "  tts: fake",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def build_plan(
    *,
    config_path: Path,
    url: str,
    data_dir: Path,
    python: str,
    session: str,
    cage: str,
) -> KioskPlan:
    return KioskPlan(
        daemon_cmd=[python, "-m", "schoolbookd", "--config", str(config_path), "serve"],
        cage_cmd=[
            cage,
            "--",
            session,
            "kiosk",
            "--url",
            url,
            "--data-dir",
            str(data_dir),
        ],
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
    parser.add_argument("--no-dev", action="store_true", help="hide the developer text box")
    args = parser.parse_args(argv)
    try:
        share = args.share_dir or find_share()
        require_ui(share)
        cage = _which("cage")
        session = _which("schoolbook-session")
        runtime = args.runtime_dir or Path.home() / ".local/share/schoolbook"
        if args.config is not None:
            config_path = args.config
        else:
            secrets_file = runtime / "etc" / "secrets.env"
            config_path = runtime / "schoolbook.yaml"
            if not (secrets_file.is_file() and config_path.is_file() and not args.parent_password):
                if not args.parent_password:
                    raise LaunchError("pass --parent-password on the first run")
                config_path = prepare_runtime(runtime, share, parent_password=args.parent_password)
        config = load_config(config_path)
        errors = check_config(config)
        if errors:
            raise LaunchError("; ".join(errors))
        query = "" if args.no_dev else "?dev=1"
        url = f"http://127.0.0.1:{config.ports.child}/{query}"
        plan = build_plan(
            config_path=config_path,
            url=url,
            data_dir=config.data_dir,
            python=sys.executable,
            session=session,
            cage=cage,
        )
        env = os.environ.copy()
        if env.get("WAYLAND_DISPLAY") or env.get("DISPLAY"):
            env.setdefault("WLR_BACKENDS", "wayland")
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
