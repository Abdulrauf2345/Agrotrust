"""In-memory metrics registry (spec section 43 stand-in for Prometheus, which needs a scrape
target/network this sandbox doesn't have). Thread-safe counters/histograms with a
Prometheus-text-format exporter, so swapping in a real `prometheus_client` later is a drop-in
replacement of this module, not a rewrite of every call site.
"""
from __future__ import annotations

import threading
from collections import defaultdict


class MetricsRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._counters: dict[tuple, float] = defaultdict(float)
        self._histograms: dict[tuple, list[float]] = defaultdict(list)

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None) -> tuple:
        return (name, tuple(sorted((labels or {}).items())))

    def increment(self, name: str, value: float = 1.0, **labels: str) -> None:
        with self._lock:
            self._counters[self._key(name, labels)] += value

    def observe(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            self._histograms[self._key(name, labels)].append(value)

    def snapshot(self) -> dict:
        with self._lock:
            counters = {self._label_str(k): v for k, v in self._counters.items()}
            histograms = {self._label_str(k): {"count": len(v), "sum": round(sum(v), 4),
                                               "avg": round(sum(v) / len(v), 4) if v else 0.0}
                         for k, v in self._histograms.items()}
        return {"counters": counters, "histograms": histograms}

    @staticmethod
    def _label_str(key: tuple) -> str:
        name, labels = key
        if not labels:
            return name
        return name + "{" + ",".join(f'{k}="{v}"' for k, v in labels) + "}"

    def prometheus_text(self) -> str:
        lines = []
        with self._lock:
            for (name, labels), v in self._counters.items():
                lines.append(f"{self._label_str((name, labels))} {v}")
            for (name, labels), values in self._histograms.items():
                base = self._label_str((name, labels))
                lines.append(f"{base}_count {len(values)}")
                lines.append(f"{base}_sum {sum(values)}")
        return "\n".join(lines) + "\n"


registry = MetricsRegistry()
