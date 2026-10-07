# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Startup self-test. Filled in with the tutor runtime."""

from __future__ import annotations

from schoolbookd.config import SchoolbookConfig, Secrets


def run_self_test(config: SchoolbookConfig, secrets: Secrets) -> int:
    del config, secrets
    raise NotImplementedError
