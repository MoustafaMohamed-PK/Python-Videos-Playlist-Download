import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.downloader import ProgressEvent
from app.progress import ProgressAggregator


def _event(index, status, downloaded=0, total=100, speed=None, title="Item"):
    return ProgressEvent(
        status=status,
        video_index=index,
        video_total=3,
        title=title,
        downloaded_bytes=downloaded,
        total_bytes=total,
        speed=speed,
        eta=None,
        quality_label="best",
    )


class TestProgressAggregator(unittest.TestCase):
    def test_empty_snapshot(self):
        agg = ProgressAggregator(total=3)
        snap = agg.snapshot()
        self.assertEqual(snap.total, 3)
        self.assertEqual(snap.completed, 0)
        self.assertEqual(snap.overall_fraction, 0.0)

    def test_single_item_downloading_fraction(self):
        agg = ProgressAggregator(total=1)
        snap = agg.update(_event(1, "downloading", downloaded=50, total=100))
        self.assertEqual(snap.overall_fraction, 0.5)
        self.assertEqual(snap.active_count, 1)

    def test_finished_item_counts_as_full(self):
        agg = ProgressAggregator(total=1)
        agg.update(_event(1, "downloading", downloaded=10, total=100))
        snap = agg.update(_event(1, "finished"))
        self.assertEqual(snap.overall_fraction, 1.0)
        self.assertEqual(snap.completed, 1)
        self.assertEqual(snap.active_count, 0)

    def test_overall_fraction_is_mean_across_items(self):
        agg = ProgressAggregator(total=2)
        agg.update(_event(1, "downloading", downloaded=100, total=100))  # 100%
        snap = agg.update(_event(2, "downloading", downloaded=0, total=100))  # 0%
        self.assertEqual(snap.overall_fraction, 0.5)

    def test_total_speed_sums_active_items_only(self):
        agg = ProgressAggregator(total=2)
        agg.update(_event(1, "downloading", downloaded=10, total=100, speed=1000))
        agg.update(_event(2, "downloading", downloaded=10, total=100, speed=2000))
        snap = agg.snapshot()
        self.assertEqual(snap.total_speed, 3000)

        # A finished item's speed no longer contributes.
        snap = agg.update(_event(1, "finished"))
        self.assertEqual(snap.total_speed, 2000)

    def test_snapshot_is_a_copy_not_live(self):
        agg = ProgressAggregator(total=1)
        first = agg.update(_event(1, "downloading", downloaded=10, total=100))
        agg.update(_event(1, "downloading", downloaded=90, total=100))
        # The earlier snapshot must not have mutated in place.
        self.assertEqual(first.items[1].fraction, 0.1)


if __name__ == "__main__":
    unittest.main()
