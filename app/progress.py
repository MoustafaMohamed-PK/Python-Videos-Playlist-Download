"""
Thread-safe progress aggregation across one or more concurrently
downloading items.

Responsible for:
    - Merging ProgressEvents (which can arrive from multiple worker
      threads at once, one per in-flight playlist item) into a single,
      consistent snapshot.
    - Computing an overall fraction/speed across all items, since a
      single "downloading N%" line no longer makes sense once more
      than one item can be in flight at a time.

Nothing here prints or blocks -- it's a pure, lock-guarded data
structure. The CLI reads snapshots to render its own display; a future
web UI would read them to serve progress over an API.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

from app.downloader import ProgressEvent


@dataclass
class ItemProgress:
    index: int
    title: str
    status: str  # "downloading" | "finished" | "error"
    fraction: float
    downloaded_bytes: Optional[float] = None
    total_bytes: Optional[float] = None
    speed: Optional[float] = None
    eta: Optional[float] = None


@dataclass
class Snapshot:
    items: Dict[int, ItemProgress] = field(default_factory=dict)
    total: int = 0

    @property
    def completed(self) -> int:
        return sum(1 for item in self.items.values() if item.status == "finished")

    @property
    def overall_fraction(self) -> float:
        """Mean of per-item fractions, finished items counted as 1.0.

        Byte-weighted averaging would be more precise, but per-item
        total sizes aren't known for items that haven't started
        downloading yet, so a simple mean across known items is the
        honest option rather than a falsely precise one.
        """
        if not self.items:
            return 0.0
        fractions = [1.0 if item.status == "finished" else item.fraction for item in self.items.values()]
        return sum(fractions) / len(self.items)

    @property
    def total_speed(self) -> float:
        return sum(item.speed or 0.0 for item in self.items.values() if item.status == "downloading")

    @property
    def active_count(self) -> int:
        return sum(1 for item in self.items.values() if item.status == "downloading")


class ProgressAggregator:
    """Merges ProgressEvents from any number of threads into one Snapshot."""

    def __init__(self, total: int):
        self._lock = threading.Lock()
        self._snapshot = Snapshot(total=total)

    def update(self, event: ProgressEvent) -> Snapshot:
        with self._lock:
            if event.status == "downloading":
                total_bytes = event.total_bytes
                downloaded = event.downloaded_bytes or 0
                fraction = (downloaded / total_bytes) if total_bytes else 0.0
                self._snapshot.items[event.video_index] = ItemProgress(
                    index=event.video_index,
                    title=event.title,
                    status="downloading",
                    fraction=fraction,
                    downloaded_bytes=event.downloaded_bytes,
                    total_bytes=event.total_bytes,
                    speed=event.speed,
                    eta=event.eta,
                )
            elif event.status == "finished":
                self._snapshot.items[event.video_index] = ItemProgress(
                    index=event.video_index,
                    title=event.title,
                    status="finished",
                    fraction=1.0,
                    downloaded_bytes=event.downloaded_bytes,
                    total_bytes=event.total_bytes,
                )
            return self._copy()

    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._copy()

    def _copy(self) -> Snapshot:
        # Shallow copy: ItemProgress instances are replaced wholesale on
        # each update, never mutated in place, so sharing them between
        # the internal snapshot and a returned copy is safe.
        return Snapshot(items=dict(self._snapshot.items), total=self._snapshot.total)
