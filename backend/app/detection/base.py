from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

Strength = Literal["weak", "moderate", "strong"]
Direction = Literal["manipulated", "synthetic", "authentic", "neutral"]
Status = Literal["ok", "unavailable", "error", "skipped"]

STRENGTH_RANK = {"weak": 1, "moderate": 2, "strong": 3}


@dataclass
class Signal:
    detector: str
    id: str
    title: str
    strength: Strength
    direction: Direction
    detail: str
    category: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    timestamp_s: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceFile:
    name: str
    kind: str  # heatmap | frame | spectrogram
    caption: str
    timestamp_s: float | None = None


@dataclass
class DetectorReport:
    name: str
    version: str
    status: Status
    reason: str | None = None
    calibrated: bool = False
    # Calibrated probability of manipulation; only set when calibrated=True.
    score: float | None = None
    thresholds: dict[str, float] | None = None
    signals: list[Signal] = field(default_factory=list)
    evidence: list[EvidenceFile] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "reason": self.reason,
            "calibrated": self.calibrated,
            "score": self.score if self.calibrated else None,
        }


@dataclass
class MediaContext:
    analysis_id: str
    data: bytes
    kind: str
    mime: str
    path: Path
    out_dir: Path
    source_url: str | None = None
    progress: Callable[[int, str], None] = lambda pct, stage: None
    cache: dict[str, Any] = field(default_factory=dict)


class Detector:
    name: str = "detector"
    version: str = "1.0"
    kinds: tuple[str, ...] = ()
    description: str = ""
    # heuristic | provenance | model
    category: str = "heuristic"

    def availability(self) -> tuple[bool, str | None]:
        return True, None

    def run(self, ctx: MediaContext) -> DetectorReport:  # pragma: no cover - interface
        raise NotImplementedError

    def report(self, status: Status = "ok", **kw) -> DetectorReport:
        return DetectorReport(name=self.name, version=self.version, status=status, **kw)
