"""Offline regression tests for arbitrary bike/run PR queries.

Run with: uv run python test_performance_queries.py
No Garmin login or database mutation is performed.
"""
from datetime import date, datetime, timedelta, timezone
import unittest
from unittest.mock import patch

import performance_queries as pq


class PeriodBoundsTests(unittest.TestCase):
    def test_none_means_all_available_history(self):
        start, end = pq._period_bounds(None, None)
        self.assertEqual(start, date.min)
        self.assertEqual(end, date.today())

    def test_all_time_aliases_mean_all_history(self):
        for alias in ("all", "all_time", "all-time", "ever", "lifetime", "entire history"):
            with self.subTest(alias=alias):
                start, end = pq._period_bounds(30, alias)
                self.assertEqual(start, date.min)
                self.assertEqual(end, date.today())

    def test_explicit_lookback_keeps_rolling_window(self):
        start, end = pq._period_bounds(180, None)
        self.assertEqual(end, date.today())
        self.assertEqual(start, date.today() - timedelta(days=179))


class EffortAlgorithmTests(unittest.TestCase):
    def test_bike_best_power_uses_exact_duration_and_time_weighted_average(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        samples = []
        for sec in range(121):
            # A steady 200 W effort followed by a 250 W 60-second block.
            power = 200.0 if sec < 60 else 250.0
            samples.append({
                "t": t0 + timedelta(seconds=sec),
                "timer_s": float(sec),
                "moving_s": float(sec),
                "elapsed_s": float(sec),
                "power": power,
            })
        result = pq._duration_effort(samples, 60, "power")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["value"], 250.0, places=6)
        self.assertEqual(result["timer_basis"], "sumDuration")

    
    def test_15_minute_pr_can_be_found_inside_a_30_minute_ride(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        samples = []

        # First 15 minutes average 200 W; second 15 average 220 W.
        for sec in range(0, 1801, 30):
            power = 200.0 if sec < 900 else 220.0
            samples.append({
                "t": t0 + timedelta(seconds=sec),
                "timer_s": float(sec),
                "moving_s": float(sec),
                "elapsed_s": float(sec),
                "power": power,
            })

        result = pq._duration_effort(samples, 900, "power")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["value"], 220.0, places=6)
        self.assertAlmostEqual(
            (result["end_timestamp"] - result["start_timestamp"])
            .total_seconds(),
            900.0,
        )


    def test_bike_effort_rejects_missing_power_inside_candidate_window(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        samples = []
        for sec in range(61):
            samples.append({
                "t": t0 + timedelta(seconds=sec),
                "timer_s": float(sec),
                "moving_s": float(sec),
                "elapsed_s": float(sec),
                "power": None if sec == 30 else 220.0,
            })
        self.assertIsNone(pq._duration_effort(samples, 60, "power"))

    def test_run_distance_effort_interpolates_exact_target_distance(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        samples = []
        for sec in range(101):
            samples.append({
                "t": t0 + timedelta(seconds=sec),
                "distance_m": float(sec * 5),
                "timer_s": float(sec),
                "moving_s": float(sec),
                "elapsed_s": float(sec),
            })
        result = pq._distance_effort(samples, 400)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["time_seconds"], 80.0, places=6)
        self.assertAlmostEqual(result["pace_seconds_per_mile"], 321.8688, places=4)
        self.assertEqual(result["timer_basis"], "sumDuration")

    
    def test_5_mile_pr_can_be_found_inside_a_10_mile_run(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        target_m = 5 * 1609.344
        total_m = 10 * 1609.344

        distances = {0.0, target_m, total_m}
        distances.update(
            float(d) for d in range(100, int(total_m), 100)
        )
        distances = sorted(distances)

        samples = []
        timer = 0.0

        for i, distance in enumerate(distances):
            if i:
                prev_distance = distances[i - 1]
                midpoint = (prev_distance + distance) / 2.0

                # First five miles at 8:20/mi; final five at 6:40/mi.
                pace = 500.0 if midpoint < target_m else 400.0
                timer += (
                    (distance - prev_distance) / 1609.344 * pace
                )

            samples.append({
                "t": t0 + timedelta(seconds=timer),
                "distance_m": distance,
                "timer_s": timer,
                "moving_s": timer,
                "elapsed_s": timer,
            })

        result = pq._distance_effort(samples, target_m)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["time_seconds"], 2000.0, places=4)
        self.assertAlmostEqual(
            result["pace_seconds_per_mile"], 400.0, places=4
        )


    def test_run_distance_effort_rejects_insufficient_distance(self):
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        samples = [{
            "t": t0 + timedelta(seconds=sec),
            "distance_m": float(sec * 5),
            "timer_s": float(sec),
            "moving_s": float(sec),
            "elapsed_s": float(sec),
        } for sec in range(20)]
        self.assertIsNone(pq._distance_effort(samples, 400))


class QuerySelectionTests(unittest.TestCase):
    class Activity:
        def __init__(self, activity_id, activity_date, activity_name, activity_type="indoor_cycling"):
            self.activity_id = activity_id
            self.activity_date = activity_date
            self.activity_name = activity_name
            self.activity_type = activity_type
            self.raw_data = "{}"

    class FakeGarmin:
        def get_activity_details(self, activity_id):
            return {"id": activity_id}

    def test_bike_query_selects_highest_power_and_passes_all_time_period(self):
        older = self.Activity(1, date(2020, 1, 1), "Older Ride")
        newer = self.Activity(2, date(2026, 10, 1), "Newer Ride")
        samples_by_id = {
            1: [{"t": datetime(2020, 1, 1, tzinfo=timezone.utc), "timer_s": 0.0, "moving_s": 0.0, "elapsed_s": 0.0, "power": 300.0},
                {"t": datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=60), "timer_s": 60.0, "moving_s": 60.0, "elapsed_s": 60.0, "power": 300.0}],
            2: [{"t": datetime(2026, 10, 1, tzinfo=timezone.utc), "timer_s": 0.0, "moving_s": 0.0, "elapsed_s": 0.0, "power": 250.0},
                {"t": datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(seconds=60), "timer_s": 60.0, "moving_s": 60.0, "elapsed_s": 60.0, "power": 250.0}],
        }
        with patch.object(pq, "_activity_query", return_value=[older, newer]) as query, \
             patch.object(pq, "get_garmin_client", return_value=self.FakeGarmin()), \
             patch.object(pq, "_detail_samples", side_effect=lambda details, sport: samples_by_id[details["id"]]), \
             patch.object(pq, "_surface", return_value="indoor"):
            result = pq.get_best_performance("bike", 60, window_days=None)
        query.assert_called_once_with("bike", None, "all_time")
        self.assertTrue(result["found"])
        self.assertEqual(result["activity_id"], 1)
        self.assertEqual(result["best_power_w"], 300.0)
        self.assertEqual(result["period"], "all_time")
        self.assertEqual(result["period_start"], "2020-01-01")
        self.assertIsNone(result["window_days"])

    def test_run_query_selects_fastest_exact_distance(self):
        slower = self.Activity(11, date(2026, 10, 1), "Slower Run", "running")
        faster = self.Activity(12, date(2026, 10, 2), "Faster Run", "running")
        samples_by_id = {
            11: [{"t": datetime(2026, 10, 1, tzinfo=timezone.utc), "distance_m": 0.0, "timer_s": 0.0, "moving_s": 0.0, "elapsed_s": 0.0},
                 {"t": datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(seconds=100), "distance_m": 400.0, "timer_s": 100.0, "moving_s": 100.0, "elapsed_s": 100.0}],
            12: [{"t": datetime(2026, 10, 2, tzinfo=timezone.utc), "distance_m": 0.0, "timer_s": 0.0, "moving_s": 0.0, "elapsed_s": 0.0},
                 {"t": datetime(2026, 10, 2, tzinfo=timezone.utc) + timedelta(seconds=80), "distance_m": 400.0, "timer_s": 80.0, "moving_s": 80.0, "elapsed_s": 80.0}],
        }
        with patch.object(pq, "_activity_query", return_value=[slower, faster]), \
             patch.object(pq, "get_garmin_client", return_value=self.FakeGarmin()), \
             patch.object(pq, "_detail_samples", side_effect=lambda details, sport: samples_by_id[details["id"]]), \
             patch.object(pq, "_surface", return_value="outdoor"), \
             patch.object(pq, "_is_treadmill", return_value=False):
            result = pq.get_best_performance("run", 400, window_days=180)
        self.assertTrue(result["found"])
        self.assertEqual(result["activity_id"], 12)
        self.assertEqual(result["time_seconds"], 80.0)
        self.assertEqual(result["window_days"], 180)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
