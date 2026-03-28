"""
trace.py — Append-only, JSON-serialisable execution trace.

Every component in the pipeline calls trace.add() to record what it did.
Nothing is ever modified after recording; the trace is write-once.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TraceStep:
    """A single immutable record in the execution trace."""

    name: str
    description: str
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class Trace:
    """
    Append-only, JSON-serialisable execution trace.

    Design notes:
    - Steps are never mutated after insertion.
    - `to_dict()` produces plain Python primitives, safe to serialise anywhere.
    - Both the HTML viewer and the JSON file produced by `save()` expose the same schema.
    """

    steps: list[TraceStep] = field(default_factory=list)

    def add(self, name: str, description: str, data: dict[str, Any]) -> None:
        """Append a new step.  Call sites must never mutate the step afterwards."""
        self.steps.append(TraceStep(name=name, description=description, data=data))

    def to_dict(self) -> dict[str, Any]:
        return {"steps": [asdict(s) for s in self.steps]}

    def save(self, path: str) -> None:
        """Write a pretty-printed UTF-8 JSON file compatible with both UIs."""
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
