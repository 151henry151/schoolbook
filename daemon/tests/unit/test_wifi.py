# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from schoolbookd.net.wifi import Wifi, WifiError


class Result:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_lists_nearby_networks() -> None:
    def run(argv: list[str], **_kwargs: object) -> Result:
        joined = " ".join(argv)
        if "wifi list" in joined:
            return Result(
                0,
                "no:ROMPSPOT:80:WPA2\nno:Grandpa\\:s:40:WPA2\nno:Cafe:20:\nyes:ROMPSPOT:80:WPA2\n",
            )
        if "rescan" in joined:
            return Result(0)
        raise AssertionError(argv)

    networks = Wifi(run=run).networks()
    assert [(net.ssid, net.signal, net.secured) for net in networks] == [
        ("ROMPSPOT", 80, True),
        ("Grandpa:s", 40, True),
        ("Cafe", 20, False),
    ]


def test_status_reads_the_active_ssid() -> None:
    def run(argv: list[str], **_kwargs: object) -> Result:
        if argv[:4] == ["nmcli", "-t", "-f", "STATE,CONNECTIVITY"]:
            return Result(0, "connected:full\n")
        if argv[:4] == ["nmcli", "-t", "-f", "NAME,TYPE"]:
            return Result(0, "lo:loopback\nROMPSPOT:802-11-wireless\n")
        raise AssertionError(argv)

    status = Wifi(run=run).status()
    assert status.connected is True
    assert status.ssid == "ROMPSPOT"
    assert status.online is True


def test_connects_with_a_password() -> None:
    seen: list[list[str]] = []

    def run(argv: list[str], **_kwargs: object) -> Result:
        seen.append(argv)
        return Result(0)

    Wifi(run=run).connect("Grandpa", "secret")
    assert seen == [["nmcli", "--wait", "30", "device", "wifi", "connect", "Grandpa", "password", "secret"]]


def test_connects_to_an_open_network_without_a_password() -> None:
    seen: list[list[str]] = []

    def run(argv: list[str], **_kwargs: object) -> Result:
        seen.append(argv)
        return Result(0)

    Wifi(run=run).connect("Cafe", "")
    assert seen == [["nmcli", "--wait", "30", "device", "wifi", "connect", "Cafe"]]


def test_connect_failure_is_a_wifi_error() -> None:
    def run(_argv: list[str], **_kwargs: object) -> Result:
        return Result(1, "", "Secrets were required, but not provided.")

    try:
        Wifi(run=run).connect("Grandpa", "")
    except WifiError as exc:
        assert "Secrets" in str(exc)
    else:
        raise AssertionError("expected WifiError")
