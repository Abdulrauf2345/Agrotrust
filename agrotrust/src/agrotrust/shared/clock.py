from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

ISO_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def to_iso(dt: datetime) -> str:
    """Fixed-width UTC ISO-8601 so lexicographic order == chronological order."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime not allowed")
    return dt.astimezone(timezone.utc).strftime(ISO_FMT)


def from_iso(value: str) -> datetime:
    return datetime.strptime(value, ISO_FMT).replace(tzinfo=timezone.utc)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FrozenClock:
    """Deterministic clock for tests."""

    def __init__(self, start: datetime | None = None):
        self._now = start or datetime(2026, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> datetime:
        self._now += timedelta(**kwargs)
        return self._now
