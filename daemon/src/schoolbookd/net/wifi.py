# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""List and join Wi-Fi networks through NetworkManager."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class WifiError(RuntimeError):
    pass


@dataclass(frozen=True)
class WifiNetwork:
    ssid: str
    signal: int
    secured: bool


@dataclass(frozen=True)
class WifiStatus:
    connected: bool
    ssid: str | None
    online: bool


def _fields(line: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


class Wifi:
    def __init__(self, run: Callable[..., Any] = subprocess.run) -> None:
        self._run = run

    def _nmcli(self, argv: list[str], timeout: float = 30) -> subprocess.CompletedProcess[str]:
        try:
            return self._run(
                ["nmcli", *argv],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise WifiError("network-manager is not installed") from exc
        except subprocess.TimeoutExpired as exc:
            raise WifiError("Wi-Fi timed out") from exc

    def status(self) -> WifiStatus:
        general = self._nmcli(["-t", "-f", "STATE,CONNECTIVITY", "general"])
        if general.returncode != 0:
            raise WifiError((general.stderr or general.stdout or "status failed").strip())
        state, _, connectivity = (general.stdout or "").strip().partition(":")
        connections = self._nmcli(["-t", "-f", "NAME,TYPE", "connection", "show", "--active"])
        ssid = None
        for line in (connections.stdout or "").splitlines():
            name, _, kind = line.partition(":")
            if kind == "802-11-wireless" and name:
                ssid = name
                break
        return WifiStatus(
            connected=state == "connected" and ssid is not None,
            ssid=ssid,
            online=connectivity == "full",
        )

    def networks(self) -> list[WifiNetwork]:
        self._nmcli(["device", "wifi", "rescan"], timeout=15)
        listed = self._nmcli(["-t", "-f", "ACTIVE,SSID,SIGNAL,SECURITY", "device", "wifi", "list"])
        if listed.returncode != 0:
            raise WifiError((listed.stderr or listed.stdout or "scan failed").strip())
        found: dict[str, WifiNetwork] = {}
        for line in (listed.stdout or "").splitlines():
            parts = _fields(line)
            if len(parts) < 4:
                continue
            _active, ssid, signal, security = parts[0], parts[1], parts[2], parts[3]
            if not ssid:
                continue
            try:
                strength = int(signal or "0")
            except ValueError:
                strength = 0
            found[ssid] = WifiNetwork(ssid=ssid, signal=strength, secured=bool(security.strip()))
        return sorted(found.values(), key=lambda net: (-net.signal, net.ssid.lower()))

    def connect(self, ssid: str, password: str = "") -> None:
        name = ssid.strip()
        if not name:
            raise WifiError("pick a network")
        argv = ["--wait", "30", "device", "wifi", "connect", name]
        if password:
            argv.extend(["password", password])
        result = self._nmcli(argv, timeout=45)
        if result.returncode != 0:
            raise WifiError((result.stderr or result.stdout or "could not join").strip())
