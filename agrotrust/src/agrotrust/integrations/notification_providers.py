"""Notification channel adapters. Real SMS/email/push/WhatsApp gateways implement
``NotificationProvider``; only mocks ship in the repository (no credentials in code)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..shared.errors import ProviderError


@dataclass(frozen=True)
class Recipient:
    user_id: str
    phone: str | None
    email: str | None


class NotificationProvider(Protocol):
    channel: str

    def send(self, recipient: Recipient, message: str) -> None: ...


class MockProvider:
    """Records messages in memory; ``fail_next(n)`` simulates provider outages."""

    def __init__(self, channel: str):
        self.channel = channel
        self.sent: list[tuple[str, str]] = []
        self._fail = 0

    def fail_next(self, n: int = 1) -> None:
        self._fail = n

    def send(self, recipient: Recipient, message: str) -> None:
        if self._fail > 0:
            self._fail -= 1
            raise ProviderError(f"{self.channel} gateway unavailable")
        target = recipient.phone if self.channel in ("SMS", "WHATSAPP") else recipient.email or recipient.user_id
        self.sent.append((target or recipient.user_id, message))


def mock_providers() -> dict[str, MockProvider]:
    return {c: MockProvider(c) for c in ("SMS", "EMAIL", "PUSH", "WHATSAPP")}
