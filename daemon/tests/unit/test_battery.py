# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from pathlib import Path

import pytest

from schoolbookd.battery import battery_status


def supply(root: Path, name: str, **values: str) -> Path:
    path = root / name
    path.mkdir()
    for key, value in values.items():
        (path / key).write_text(value + "\n")
    return path


def test_reads_cf30_battery_and_ignores_ac_and_peripherals(tmp_path: Path) -> None:
    supply(tmp_path, "AC", type="Mains", online="1")
    supply(tmp_path, "A-mouse", type="Battery", scope="Device", capacity="10", status="Discharging")
    supply(tmp_path, "BATA", type="Battery", present="1", capacity="82", status="Charging")
    assert battery_status(tmp_path) == {"percent": 82, "charging": True}


@pytest.mark.parametrize("capacity", ["0", "20", "100"])
def test_discharging_including_empty_battery(tmp_path: Path, capacity: str) -> None:
    supply(tmp_path, "BAT0", type="Battery", capacity=capacity, status="Discharging")
    assert battery_status(tmp_path) == {"percent": int(capacity), "charging": False}


@pytest.mark.parametrize("capacity", ["garbage", "-1", "101"])
def test_invalid_reading_is_unknown_not_empty(tmp_path: Path, capacity: str) -> None:
    supply(tmp_path, "BAT0", type="Battery", capacity=capacity, status="Unknown")
    assert battery_status(tmp_path)["percent"] is None


def test_absent_and_unreadable_batteries(tmp_path: Path) -> None:
    supply(tmp_path, "BAT0", type="Battery", present="0", capacity="80", status="Unknown")
    supply(tmp_path, "BAT1", type="Battery")
    assert battery_status(tmp_path) == {"percent": None, "charging": False}
    assert battery_status(tmp_path / "missing") == {"percent": None, "charging": False}
