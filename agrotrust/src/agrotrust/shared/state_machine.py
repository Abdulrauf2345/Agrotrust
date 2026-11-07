"""Explicit, table-driven state machines. No arbitrary status updates."""
from __future__ import annotations

from typing import Iterable, Mapping

from .errors import InvalidStateTransition


class StateMachine:
    def __init__(self, name: str, transitions: Mapping[str, Iterable[str]]):
        self.name = name
        self._t = {k: frozenset(v) for k, v in transitions.items()}
        states = set(self._t) | {s for v in self._t.values() for s in v}
        for s in states:
            self._t.setdefault(s, frozenset())
        self.states = frozenset(states)

    def allowed(self, current: str) -> frozenset[str]:
        if current not in self.states:
            raise InvalidStateTransition(f"{self.name}: unknown state {current!r}")
        return self._t[current]

    def can(self, current: str, new: str) -> bool:
        return new in self.allowed(current)

    def assert_can(self, current: str, new: str) -> None:
        if not self.can(current, new):
            raise InvalidStateTransition(
                f"{self.name}: cannot go from {current} to {new}",
                details={"machine": self.name, "from": current, "to": new,
                         "allowed": sorted(self.allowed(current))},
            )

    def is_terminal(self, state: str) -> bool:
        return not self.allowed(state)

    def as_mermaid(self) -> str:
        lines = ["stateDiagram-v2"]
        for src in sorted(self._t):
            for dst in sorted(self._t[src]):
                lines.append(f"    {src} --> {dst}")
        return "\n".join(lines)
