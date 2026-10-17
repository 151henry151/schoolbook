# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Read the laptop battery without starting a process or requiring a desktop bus."""

from pathlib import Path


def battery_status(root: Path = Path("/sys/class/power_supply")) -> dict[str, object]:
    try:
        supplies = sorted(root.iterdir())
    except OSError:
        supplies = []
    for supply in supplies:
        try:
            if (supply / "type").read_text().strip() != "Battery":
                continue
            if (supply / "scope").exists() and (supply / "scope").read_text().strip() == "Device":
                continue
            if (supply / "present").exists() and (supply / "present").read_text().strip() == "0":
                continue
            percent = int((supply / "capacity").read_text().strip())
            if not 0 <= percent <= 100:
                continue
            status = (supply / "status").read_text().strip()
        except (OSError, ValueError):
            continue
        return {"percent": percent, "charging": status == "Charging"}
    return {"percent": None, "charging": False}
