import unittest

from vprobe import stats


class TestMedian(unittest.TestCase):
    def test_odd(self):
        self.assertEqual(stats.median([3, 1, 2]), 2)

    def test_even(self):
        self.assertEqual(stats.median([4, 1, 3, 2]), 2.5)

    def test_empty(self):
        self.assertIsNone(stats.median([]))

    def test_single(self):
        self.assertEqual(stats.median([7.5]), 7.5)


class TestQuantile(unittest.TestCase):
    def test_ends(self):
        values = [1, 2, 3, 4, 5]
        self.assertEqual(stats.quantile(values, 0.0), 1)
        self.assertEqual(stats.quantile(values, 1.0), 5)

    def test_middle(self):
        self.assertEqual(stats.quantile([1, 2, 3, 4, 5], 0.5), 3)

    def test_interpolates(self):
        self.assertAlmostEqual(stats.quantile([1, 2], 0.5), 1.5)

    def test_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            stats.quantile([1, 2], 1.5)


class TestBps(unittest.TestCase):
    def test_one_tick_on_ten_thousand(self):
        self.assertAlmostEqual(stats.bps(10_001, 10_000), 1.0)

    def test_negative(self):
        self.assertAlmostEqual(stats.bps(9_999, 10_000), -1.0)

    def test_zero_reference(self):
        with self.assertRaises(ZeroDivisionError):
            stats.bps(1, 0)


class TestSpread(unittest.TestCase):
    def test_spread_of_one_cent_on_a_hundred(self):
        # mid 100.005, one cent wide -> 0.99995 bps
        self.assertAlmostEqual(stats.spread_bps(100.0, 100.01), 0.99995, places=5)

    def test_tight_book(self):
        self.assertAlmostEqual(stats.spread_bps(62_500.0, 62_500.1), 0.016, places=3)

    def test_mid(self):
        self.assertEqual(stats.mid(99.0, 101.0), 100.0)

    def test_rejects_crossed(self):
        # a crossed book is still arithmetically definable; the parser drops it,
        # not the formula. Guard the divide-by-zero case here instead.
        with self.assertRaises(ValueError):
            stats.spread_bps(-1.0, 1.0)


class TestIntervals(unittest.TestCase):
    def test_median_gap(self):
        self.assertEqual(stats.median_interval_ms([0, 100, 200, 350]), 100.0)

    def test_needs_two(self):
        self.assertIsNone(stats.median_interval_ms([5]))


if __name__ == "__main__":
    unittest.main()
