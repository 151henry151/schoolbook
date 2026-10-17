# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors
"""Keep provider usage counters, never conversation content or credentials."""
from __future__ import annotations

import math

_COUNTERS = {"total_tokens", "input_tokens", "output_tokens", "cached_tokens", "text_tokens",
             "audio_tokens", "image_tokens", "reasoning_tokens", "seconds", "duration_seconds"}
_DETAILS = {"input_token_details", "output_token_details", "cached_tokens_details",
            "input_tokens_details", "output_tokens_details"}


def usage_counters(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, object] = {}
    for key, value in raw.items():
        if (key in _COUNTERS and type(value) in (int, float)
                and math.isfinite(value) and value >= 0):
            result[key] = value
        elif key in _DETAILS:
            result[key] = usage_counters(value)
        elif key == "type" and value in ("tokens", "duration"):
            result[key] = value
    return result
