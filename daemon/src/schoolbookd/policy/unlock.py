# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Parent password checks with a five-failure lockout."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_HASHER = PasswordHasher()


@dataclass
class UnlockState:
    failures: int = 0
    locked_until: datetime | None = None


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _HASHER.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def attempt_unlock(
    password: str,
    password_hash: str,
    state: UnlockState,
    now: datetime,
    *,
    limit: int = 5,
    lock_seconds: int = 300,
) -> tuple[bool, UnlockState]:
    if state.locked_until is not None and now < state.locked_until:
        return False, state
    if verify_password(password, password_hash):
        return True, UnlockState()
    failures = state.failures + 1
    locked_until = None
    if failures >= limit:
        locked_until = now + timedelta(seconds=lock_seconds)
        failures = 0
    return False, UnlockState(failures=failures, locked_until=locked_until)
