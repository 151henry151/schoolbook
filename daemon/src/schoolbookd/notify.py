# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Optional high-severity alerts. ntfy is off unless a URL and topic are set."""

from __future__ import annotations

import httpx


def ntfy_target(base_url: str, topic: str) -> str:
    return f"{base_url.rstrip('/')}/{topic}"


class Notifier:
    def __init__(
        self,
        ntfy_url: str | None = None,
        ntfy_topic: str | None = None,
        email_to: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.ntfy_url = ntfy_url
        self.ntfy_topic = ntfy_topic
        self.email_to = email_to
        self._client = client
        self.sent: list[dict[str, str]] = []

    def send(self, title: str, message: str) -> bool:
        self.sent.append({"title": title, "message": message, "email": self.email_to or ""})
        if not self.ntfy_url or not self.ntfy_topic:
            return False
        client = self._client or httpx.Client(timeout=5)
        response = client.post(
            ntfy_target(self.ntfy_url, self.ntfy_topic),
            headers={"Title": title},
            content=message.encode(),
        )
        response.raise_for_status()
        return True
