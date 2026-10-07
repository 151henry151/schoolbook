# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Process entry for the child UI and parent console."""

from __future__ import annotations

from schoolbookd.config import SchoolbookConfig, Secrets


def serve(config: SchoolbookConfig, secrets: Secrets) -> None:
    del config, secrets
    raise NotImplementedError
