"""On-demand performance benchmarks and range-based time-in-zone queries."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import math
from statistics import mean
from typing import Any

from activity_details import parse_activity_details
from database import Activity, AthleteProfile, get_session, initialize_database
from garmin_client import GarminClient, get_garmin_client
from performance_engine import _sport, _is_treadmill, _first


SPORTS = {"run", "bike", "swim"}
ZONE_KEYS = tuple(str(i) for i in range(1, 7))


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _pace_from_seconds_per_mile(seconds):
    seconds = _num(seconds)
    if seconds is None or seconds <= 0:
        return None
    n = int(round(seconds))
    return f"{n // 60}:{n % 60:02d}/mi"


def _pace_from_seconds_per_100m(seconds):
    seconds = _num(seconds)
    if seconds is None or seconds <= 0:
        return None
    n = int(round(seconds))
    return f"{n // 60}:{n % 60:02d}/100m"


def _coerce_timestamp(value):
    """Normalize Garmin timestamps to timezone-aware UTC datetimes."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        try:
            seconds = float(value)
            if seconds > 10_000_000_000:
                seconds /= 1000.0
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _activity_start(activity: Activity) -> datetime:
    raw = getattr(activity, "raw_data", None)
    if raw:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            for key in ("startTimeLocal", "startTimeGMT", "startTime", "activityStartTime"):
                value = data.get(key)
                parsed = _coerce_timestamp(value)
                if parsed:
                    return parsed
        except Exception:
            pass
    activity_date = getattr(activity, "activity_date", None)
    return datetime.combine(activity_date, datetime.min.time(), tzinfo=timezone.utc) if activity_date else datetime.min.replace(tzinfo=timezone.utc)

def _period_bounds(window_days: int | None, period: str | None):
    """Return inclusive [start, end] dates; None/all-time means all history."""
    today = date.today()
    p = (period or "").lower().strip().replace("-", "_").replace(" ", "_")
    if p in {"all", "all_time", "alltime", "ever", "lifetime", "entire_history"} or (not p and window_days is None):
        # Use the minimum representable date so historical records are not
        # silently truncated to an arbitrary lookback window.
        return date.min, today
    if p in {"month", "calendar_month", "current_month"}:
        start = today.replace(day=1)
        if start.month == 12:
            end = date(start.year, 12, 31)
        else:
            end = date(start.year, start.month + 1, 1) - timedelta(days=1)
        return start, end
    if p in {"previous_month", "prev_month", "last_month"}:
        this_start = today.replace(day=1)
        end = this_start - timedelta(days=1)
        return end.replace(day=1), end
    if p in {"week", "calendar_week", "current_week"}:
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if p in {"previous_week", "prev_week", "last_week"}:
        end = today - timedelta(days=today.weekday() + 1)
        return end - timedelta(days=6), end
    days = max(1, int(window_days or 30))
    return today - timedelta(days=days - 1), today


def _activity_query(sport: str, window_days: int | None = 30, period: str | None = None):
    start, end = _period_bounds(window_days, period)
    session = get_session()
    try:
        rows = (
            session.query(Activity)
            .filter(Activity.activity_date >= start, Activity.activity_date <= end)
            .order_by(Activity.activity_date.asc(), Activity.activity_id.asc())
            .all()
        )
        return [a for a in rows if _sport(a) == sport]
    finally:
        session.close()

def _detail_samples(details, sport: str):
    """
    Parse Garmin detail samples while preserving Garmin's cumulative
    distance/time counters.

    For running performance benchmarks:
      - sumDistance = authoritative cumulative distance when available
      - sumDuration = Garmin timer/moving-time basis
      - sumMovingDuration = cross-check for moving time
      - sumElapsedDuration = elapsed/wall-clock basis

    We intentionally retain directTimestamp separately because timestamp
    gaps are useful for detecting pauses/data gaps.
    """
    out = []

    for row in parse_activity_details(details):
        raw_timestamp = row.get("timestamp") or row.get("directTimestamp")
        t = _coerce_timestamp(raw_timestamp)

        if t is None:
            continue

        speed = (
            _first(
                row,
                "directSpeed",
                "speed",
                "directEnhancedSpeed",
                "enhancedSpeed",
            )
            if sport == "run"
            else None
        )

        power = (
            _first(row, "directPower", "power", "averagePower")
            if sport == "bike"
            else None
        )

        hr = _first(row, "directHeartRate", "heartRate", "averageHR")

        # Garmin cumulative counters.
        distance_m = _first(
            row,
            "sumDistance",
            "distance",
            "distanceMeters",
        )

        timer_s = _first(
            row,
            "sumDuration",
            "duration",
            "durationSeconds",
        )

        moving_s = _first(
            row,
            "sumMovingDuration",
            "movingDuration",
            "movingDurationSeconds",
        )

        elapsed_s = _first(
            row,
            "sumElapsedDuration",
            "elapsedDuration",
            "elapsedDurationSeconds",
        )

        cadence = _first(
            row,
            "directBikeCadence",
            "directCadence",
            "bikeCadence",
            "cadence",
            "directRunCadence",
            "runCadence",
        )

        speed = _num(speed)
        power = _num(power)
        hr = _num(hr)

        if sport == "run" and (speed is None or speed <= 0):
            speed = None

        if sport == "bike" and (power is None or power < 0):
            power = None

        if hr is not None and not (25 <= hr <= 240):
            hr = None

        out.append(
            {
                "t": t,
                "speed": speed,
                "power": power,
                "hr": hr,
                "distance_m": distance_m,
                "timer_s": timer_s,
                "moving_s": moving_s,
                "elapsed_s": elapsed_s,
                "cadence": cadence,
            }
        )

    # Preserve Garmin sample order.
    return sorted(out, key=lambda x: x["t"])

def _distance_effort(samples, target_m):
    """
    Fastest contiguous run segment covering exactly target_m.

    Uses Garmin cumulative distance and Garmin timer duration when available.

    The benchmark time basis is sumDuration (timer/moving time), NOT wall-clock
    timestamp difference. This prevents pauses from inflating or corrupting
    running performance.

    Boundary samples are linearly interpolated so the requested distance is
    exactly represented rather than being forced to lap/sample boundaries.
    """
    if len(samples) < 2 or target_m <= 0:
        return None

    # We need monotonic cumulative distance and timer values.
    usable = []

    for sample in samples:
        distance_m = _num(sample.get("distance_m"))
        timer_s = _num(sample.get("timer_s"))

        if distance_m is None or timer_s is None:
            continue

        if distance_m < 0 or timer_s < 0:
            continue

        usable.append(
            {
                **sample,
                "distance_m": distance_m,
                "timer_s": timer_s,
                "moving_s": _num(sample.get("moving_s")),
                "elapsed_s": _num(sample.get("elapsed_s")),
            }
        )

    if len(usable) < 2:
        return None

    # Reject non-monotonic Garmin counters rather than fabricating a result.
    cleaned = [usable[0]]

    for sample in usable[1:]:
        previous = cleaned[-1]

        if sample["distance_m"] < previous["distance_m"]:
            continue

        if sample["timer_s"] < previous["timer_s"]:
            continue

        cleaned.append(sample)

    samples = cleaned

    if len(samples) < 2:
        return None

    total_distance = samples[-1]["distance_m"] - samples[0]["distance_m"]

    if total_distance < target_m:
        return None

    def interpolate_at_distance(target_distance):
        """
        Return cumulative timer/moving/elapsed counters at an exact
        cumulative-distance boundary.
        """
        for i in range(1, len(samples)):
            left = samples[i - 1]
            right = samples[i]

            dl = left["distance_m"]
            dr = right["distance_m"]

            if target_distance < dl or target_distance > dr:
                continue

            distance_span = dr - dl

            if distance_span <= 0:
                if target_distance == dl:
                    return {
                        "distance_m": target_distance,
                        "timer_s": left["timer_s"],
                        "moving_s": left.get("moving_s"),
                        "elapsed_s": left.get("elapsed_s"),
                        "timestamp": left["t"],
                    }
                continue

            fraction = (target_distance - dl) / distance_span

            timer_s = left["timer_s"] + (
                right["timer_s"] - left["timer_s"]
            ) * fraction

            moving_left = left.get("moving_s")
            moving_right = right.get("moving_s")

            moving_s = None
            if moving_left is not None and moving_right is not None:
                moving_s = moving_left + (
                    moving_right - moving_left
                ) * fraction

            elapsed_left = left.get("elapsed_s")
            elapsed_right = right.get("elapsed_s")

            elapsed_s = None
            if elapsed_left is not None and elapsed_right is not None:
                elapsed_s = elapsed_left + (
                    elapsed_right - elapsed_left
                ) * fraction

            timestamp = left["t"] + (
                right["t"] - left["t"]
            ) * fraction

            return {
                "distance_m": target_distance,
                "timer_s": timer_s,
                "moving_s": moving_s,
                "elapsed_s": elapsed_s,
                "timestamp": timestamp,
            }

        return None

    best = None

    # Every sample can serve as a candidate starting point.
    for start in samples:
        start_distance = start["distance_m"]
        end_distance = start_distance + target_m

        if end_distance > samples[-1]["distance_m"]:
            break

        start_point = interpolate_at_distance(start_distance)
        end_point = interpolate_at_distance(end_distance)

        if start_point is None or end_point is None:
            continue

        timer_time = end_point["timer_s"] - start_point["timer_s"]

        if timer_time <= 0:
            continue

        elapsed_time = None
        if (
            start_point.get("elapsed_s") is not None
            and end_point.get("elapsed_s") is not None
        ):
            elapsed_time = (
                end_point["elapsed_s"] - start_point["elapsed_s"]
            )

        moving_time = None
        if (
            start_point.get("moving_s") is not None
            and end_point.get("moving_s") is not None
        ):
            moving_time = (
                end_point["moving_s"] - start_point["moving_s"]
            )

        # Garmin sumDuration is our authoritative benchmark basis.
        # sumMovingDuration is a cross-check only.
        if moving_time is not None:
            counter_difference = abs(timer_time - moving_time)

            # Small differences can occur because Garmin counters are
            # sampled/rounded independently.
            counter_consistent = counter_difference <= max(2.0, timer_time * 0.01)
        else:
            counter_consistent = None

        pause_seconds = None
        if elapsed_time is not None:
            pause_seconds = max(0.0, elapsed_time - timer_time)

        candidate = {
            "time_seconds": timer_time,
            "pace_seconds_per_mile": (
                timer_time / target_m * 1609.344
            ),
            "start_timestamp": start_point["timestamp"],
            "end_timestamp": end_point["timestamp"],
            "elapsed_time_seconds": elapsed_time,
            "moving_time_seconds": moving_time,
            "pause_seconds": pause_seconds,
            "timer_basis": "sumDuration",
            "moving_counter_consistent": counter_consistent,
            "data_quality": {
                "distance_source": "sumDistance",
                "time_source": "sumDuration",
                "elapsed_source": (
                    "sumElapsedDuration"
                    if elapsed_time is not None
                    else None
                ),
                "moving_crosscheck": (
                    "sumMovingDuration"
                    if moving_time is not None
                    else None
                ),
            },
        }

        if (
            best is None
            or candidate["time_seconds"] < best["time_seconds"]
        ):
            best = candidate

    return best

def _duration_effort(samples, target_seconds, metric):
    """Best exact-duration rolling, time-weighted average of a metric.

    Uses Garmin's cumulative timer/moving-time counter as the duration axis.
    Paused wall-clock time therefore does not count toward the requested
    effort duration. Metric values are integrated with a trapezoidal rule
    over timer time, with exact interpolation at the start boundary.
    """
    if len(samples) < 2 or target_seconds <= 0:
        return None

    usable = []

    for sample in samples:
        timestamp = sample.get("t")
        timer_s = _num(sample.get("timer_s"))
        moving_s = _num(sample.get("moving_s"))
        elapsed_s = _num(sample.get("elapsed_s"))
        value = _num(sample.get(metric))

        if timestamp is None or timer_s is None:
            continue

        if timer_s < 0:
            continue

        usable.append(
            {
                **sample,
                "timer_s": timer_s,
                "moving_s": moving_s,
                "elapsed_s": elapsed_s,
                metric: value,
            }
        )

    if len(usable) < 2:
        return None

    usable.sort(key=lambda x: x["t"])

    # Garmin cumulative counters must not decrease.
    cleaned = [usable[0]]

    for sample in usable[1:]:
        previous = cleaned[-1]

        if sample["timer_s"] < previous["timer_s"]:
            continue

        cleaned.append(sample)

    samples = cleaned

    if len(samples) < 2:
        return None

    def interpolate_at_timer(target_timer):
        """Return sample values at an exact Garmin timer position.

        Duplicate timer values represent paused wall-clock time. When the
        requested timer lands on such a duplicate, use the latest sample at
        that timer so diagnostics land after the pause.
        """
        if (
            target_timer < samples[0]["timer_s"]
            or target_timer > samples[-1]["timer_s"]
        ):
            return None

        exact_index = None

        for i, sample in enumerate(samples):
            timer = sample["timer_s"]

            if timer == target_timer:
                exact_index = i
                continue

            if timer > target_timer:
                if exact_index is not None:
                    sample = samples[exact_index]

                    return {
                        "timer_s": target_timer,
                        "t": sample["t"],
                        "elapsed_s": sample.get("elapsed_s"),
                        "moving_s": sample.get("moving_s"),
                        "value": _num(sample.get(metric)),
                    }

                left = samples[i - 1]
                right = sample

                dt_timer = right["timer_s"] - left["timer_s"]

                if dt_timer <= 0:
                    return None

                fraction = (
                    target_timer - left["timer_s"]
                ) / dt_timer

                return {
                    "timer_s": target_timer,
                    "t": (
                        left["t"]
                        + (right["t"] - left["t"]) * fraction
                    ),
                    "elapsed_s": (
                        left["elapsed_s"]
                        + (
                            right["elapsed_s"]
                            - left["elapsed_s"]
                        )
                        * fraction
                        if (
                            left.get("elapsed_s") is not None
                            and right.get("elapsed_s") is not None
                        )
                        else None
                    ),
                    "moving_s": (
                        left["moving_s"]
                        + (
                            right["moving_s"]
                            - left["moving_s"]
                        )
                        * fraction
                        if (
                            left.get("moving_s") is not None
                            and right.get("moving_s") is not None
                        )
                        else None
                    ),
                    "value": (
                        left[metric]
                        + (
                            right[metric]
                            - left[metric]
                        )
                        * fraction
                        if (
                            left.get(metric) is not None
                            and right.get(metric) is not None
                        )
                        else None
                    ),
                }

        if exact_index is not None:
            sample = samples[exact_index]

            return {
                "timer_s": target_timer,
                "t": sample["t"],
                "elapsed_s": sample.get("elapsed_s"),
                "moving_s": sample.get("moving_s"),
                "value": _num(sample.get(metric)),
            }

        return None

    def window_average(end_i):
        end = samples[end_i]

        end_timer = end["timer_s"]
        start_timer = end_timer - target_seconds

        if start_timer < samples[0]["timer_s"]:
            return None

        start_boundary = interpolate_at_timer(start_timer)

        if start_boundary is None:
            return None

        integral = 0.0
        covered = 0.0
        cursor = end_i

        # Integrate over Garmin timer time.
        #
        # If timer_s does not advance between samples, that represents
        # paused wall-clock time and contributes zero riding duration.
        while cursor > 0:
            left = samples[cursor - 1]
            right = samples[cursor]

            left_timer = left["timer_s"]
            right_timer = right["timer_s"]

            dt_timer = right_timer - left_timer

            if dt_timer < 0:
                return None

            # Paused interval: wall clock may advance while Garmin's
            # cumulative timer remains unchanged.
            if dt_timer == 0:
                cursor -= 1
                continue

            if right_timer <= start_timer:
                break

            segment_start = max(
                left_timer,
                start_timer,
            )

            segment_end = min(
                right_timer,
                end_timer,
            )

            if segment_end <= segment_start:
                cursor -= 1
                continue

            left_value = _num(left.get(metric))
            right_value = _num(right.get(metric))

            # A missing metric over any portion of the actual effort makes
            # this candidate unreliable.
            if left_value is None or right_value is None:
                return None

            # Interpolate the metric at the exact start boundary.
            start_fraction = (
                segment_start - left_timer
            ) / dt_timer

            end_fraction = (
                segment_end - left_timer
            ) / dt_timer

            value_start = (
                left_value
                + (right_value - left_value)
                * start_fraction
            )

            value_end = (
                left_value
                + (right_value - left_value)
                * end_fraction
            )

            used_seconds = segment_end - segment_start

            integral += (
                (value_start + value_end) / 2.0
            ) * used_seconds

            covered += used_seconds

            if segment_start <= start_timer:
                break

            cursor -= 1

        # Require essentially the full requested duration.
        if covered < target_seconds * 0.98:
            return None

        average = integral / covered

        
        end_elapsed = end.get("elapsed_s")
        end_moving = end.get("moving_s")

        start_elapsed = start_boundary.get("elapsed_s")
        start_moving = start_boundary.get("moving_s")

        elapsed_time = (
            end_elapsed - start_elapsed
            if (
                end_elapsed is not None
                and start_elapsed is not None
            )
            else None
        )

        # Garmin's sumMovingDuration is not reliable for every activity type
        # (notably some indoor cycling activities). Never report 0 moving seconds
        # merely because the Garmin moving counter is absent or non-advancing.
        moving_counter_delta = (
            end_moving - start_moving
            if (
                end_moving is not None
                and start_moving is not None
            )
            else None
        )

        if moving_counter_delta is not None and moving_counter_delta > 0:
            moving_time = moving_counter_delta
            moving_counter_consistent = (
                abs(moving_time - covered) <= 2.0
            )
        else:
            # The benchmark is explicitly based on Garmin's timer duration.
            # Fall back to the actual covered timer duration rather than
            # fabricating a 0-second moving time.
            moving_time = covered
            moving_counter_consistent = None

        pause_seconds = (
            max(0.0, elapsed_time - covered)
            if elapsed_time is not None
            else None
        )


        return {
            "value": average,
            "start_timestamp": start_boundary["t"],
            "end_timestamp": end["t"],
            "timer_basis": "sumDuration",
            "elapsed_time_seconds": elapsed_time,
            "moving_time_seconds": moving_time,
            "pause_seconds": pause_seconds,
            "moving_counter_consistent": (
                moving_counter_consistent
            ),
            "covered_seconds": covered,
        }

    best = None

    for end_i in range(1, len(samples)):
        candidate = window_average(end_i)

        if candidate is None:
            continue

        if (
            best is None
            or candidate["value"] > best["value"]
        ):
            best = candidate

    return best

def _swim_lengths(splits):
    rows = []
    for lap in (splits or {}).get("lapDTOs", []) or []:
        for length in lap.get("lengthDTOs", []) or []:
            dist = _num(_first(length, "distance", "distanceMeters", "lengthDistance", "distanceInMeters"))
            dur = _num(_first(length, "duration", "durationSeconds", "lengthDuration"))
            if dist is None or dur is None or dist <= 0 or dur <= 0:
                continue
            pace100 = dur / dist * 100.0
            # Reject physically impossible Garmin length records. This is
            # deliberately conservative enough for swimming and kick work.
            if pace100 < 20.0 or pace100 > 300.0:
                continue
            stroke = str(length.get("swimStroke") or length.get("strokeType") or length.get("stroke") or lap.get("swimStroke") or lap.get("strokeType") or "").upper()
            rows.append({"distance_m": dist, "duration_s": dur, "stroke": stroke})
    return rows


# ---------------------------------------------------------------------------
# Swim PR (best distance) logic.
#
# Plausibility bounds are expressed in seconds per 100 m. Distance is always
# meters and time is always seconds; every check converts to this one unit so
# it applies identically to a single length and to a whole candidate effort.
#   floor   36.0 s/100 m (= 2.78 m/s: 25 m in 9.0 s, 50 m in 18.0 s). An
#           effort can never average faster than the fastest single length in
#           it, and the fastest length anyone swims is an elite sprint with a
#           dive start, roughly 9-10 s per 25 m (36-40 s/100 m); the 50 m
#           freestyle record (~20-21 s, ~42 s/100 m average) fits that. The
#           floor sits at the fast end of that range, i.e. below any realistic
#           swim, while still rejecting Garmin timing artifacts (100 m in
#           0.7 s; 25 m lengths of 1.6 s, 2.1 s and 6.05 s). One constant is
#           applied to every single length and every complete candidate effort.
#   ceiling 300.0 s/100 m (unchanged from the previous implementation).
# ---------------------------------------------------------------------------
_SWIM_PR_MIN_PACE_S_PER_100M = 36.0
_SWIM_PR_MAX_PACE_S_PER_100M = 300.0
_SWIM_PR_DISTANCE_TOL_M = 0.05
# Garmin length start times are truncated to whole seconds, so consecutive
# lengths legitimately differ from (start + duration) by up to ~1 s.
_SWIM_PR_CONTINUITY_TOL_S = 1.05
_SWIM_PR_REST_MARKERS = ("REST", "IDLE")


def _swim_pr_epoch(value):
    """Garmin length start time -> epoch seconds, tolerant of '...:07.0'."""
    parsed = _coerce_timestamp(value)
    if parsed is not None:
        return parsed.timestamp()
    if isinstance(value, str) and "." in value:
        head, _, frac = value.strip().partition(".")
        digits = "".join(ch for ch in frac if ch.isdigit())
        base = _coerce_timestamp(head)
        if base is not None:
            return base.timestamp() + (float("0." + digits) if digits else 0.0)
    return None


def _swim_pr_text(record, *keys):
    for key in keys:
        value = record.get(key)
        if value:
            return str(value).strip().upper()
    return ""


def _swim_pr_pace_ok(distance_m, duration_s):
    if distance_m is None or duration_s is None or distance_m <= 0 or duration_s <= 0:
        return False
    pace100 = duration_s / distance_m * 100.0
    return _SWIM_PR_MIN_PACE_S_PER_100M <= pace100 <= _SWIM_PR_MAX_PACE_S_PER_100M


def _swim_pr_sequence(splits, pool_m=None):
    """Ordered Garmin swim records for PR search.

    pool_m is the expected length distance in meters (from a validated course);
    when None it is the most common recorded length distance.

    Returns a list whose items are either a valid-length dict or None. None is
    a barrier: a rest record, an excluded record (drill, zero-stroke,
    malformed, implausible, partial length) or a lap whose lengths cannot be
    verified. Nothing is ever dropped silently, so lengths on either side of a
    barrier are never joined.
    """
    seq = []
    pool_counts = {}

    for lap in (splits or {}).get("lapDTOs", []) or []:
        lap_dist = _num(_first(lap, "distance", "distanceMeters"))
        lap_stroke = _swim_pr_text(lap, "swimStroke", "strokeType", "stroke")
        lap_intensity = _swim_pr_text(lap, "intensityType", "wktIntensityType")
        lengths = lap.get("lengthDTOs") or []

        # A lap explicitly tagged as rest is a hard barrier and none of its
        # length records are trusted, even if they carry a distance.
        if lap_stroke in _SWIM_PR_REST_MARKERS or lap_intensity in _SWIM_PR_REST_MARKERS:
            seq.append(None)
            continue
        if lap_dist is None or lap_dist <= 0 or not lengths:
            seq.append(None)

        for length in lengths:
            dist = _num(_first(length, "distance", "distanceMeters", "lengthDistance", "distanceInMeters"))
            dur = _num(_first(length, "duration", "durationSeconds", "lengthDuration"))
            stroke = _swim_pr_text(length, "swimStroke", "strokeType", "stroke")
            marker = _swim_pr_text(length, "lengthType", "intensityType", "wktIntensityType")

            # Rest records have no distance (or an explicit rest marker).
            if dist is None or dist <= 0 or stroke in _SWIM_PR_REST_MARKERS or marker in _SWIM_PR_REST_MARKERS:
                seq.append(None)
                continue
            if dur is None or dur <= 0:
                seq.append(None)
                continue

            pool_counts[round(dist, 2)] = pool_counts.get(round(dist, 2), 0) + 1

            if not stroke and lap_stroke not in ("", "MIXED") + _SWIM_PR_REST_MARKERS:
                stroke = lap_stroke
            strokes = _num(_first(length, "totalNumberOfStrokes", "strokes", "totalStrokes"))

            if (
                not stroke
                or stroke == "MIXED"
                or "DRILL" in stroke
                or (strokes is not None and strokes <= 0)
                or not _swim_pr_pace_ok(dist, dur)
            ):
                seq.append(None)
                continue

            index = _num(length.get("lengthIndex"))
            seq.append({
                "distance_m": dist,
                "duration_s": dur,
                "stroke": stroke,
                "index": int(round(index)) if index is not None else None,
                "start": _swim_pr_epoch(length.get("startTimeGMT") or length.get("startTime")),
            })

    # Pool length = the validated course length when given, else the most common
    # recorded length distance. Any length that is not a full pool length is a
    # partial/non-standard length: also a barrier.
    if pool_m is None and pool_counts:
        pool_m = max(pool_counts.items(), key=lambda item: item[1])[0]
    if pool_m is not None:
        seq = [
            rec if rec is None or abs(rec["distance_m"] - pool_m) <= _SWIM_PR_DISTANCE_TOL_M else None
            for rec in seq
        ]
    return seq


def _swim_pr_continuous(prev, cur):
    """True only if the two lengths are provably back-to-back."""
    index_ok = None
    if prev["index"] is not None and cur["index"] is not None:
        index_ok = cur["index"] - prev["index"] == 1
    time_ok = None
    if prev["start"] is not None and cur["start"] is not None:
        gap = cur["start"] - (prev["start"] + prev["duration_s"])
        time_ok = abs(gap) <= _SWIM_PR_CONTINUITY_TOL_S
    if index_ok is False or time_ok is False:
        return False
    return index_ok is True or time_ok is True


def _swim_pr_runs(seq):
    """Split into continuous, single-stroke runs of valid lengths."""
    runs, cur = [], []
    for rec in seq:
        if rec is None:
            if cur:
                runs.append(cur)
            cur = []
            continue
        if cur and (rec["stroke"] != cur[-1]["stroke"] or not _swim_pr_continuous(cur[-1], rec)):
            runs.append(cur)
            cur = []
        cur.append(rec)
    if cur:
        runs.append(cur)
    return runs


# ---------------------------------------------------------------------------
# Pool courses (meters vs yards).
#
# Garmin stores pool_length in centimeters (2500 = 25 m, 2286 = 25 yd) and
# records every length distance in meters (a 25-yard length is 22.86 m). A
# session is only assigned a course when the pool_length metadata names a
# supported pool AND the lengths recorded in the splits have that same size.
# Missing, unsupported or conflicting metadata leaves the session unclassified;
# it is never guessed from a distance that happens to convert to a target.
# ---------------------------------------------------------------------------
_SWIM_UNIT_M = {"meters": 1.0, "yards": 0.9144}
_SWIM_UNIT_ABBR = {"meters": "m", "yards": "yd"}
_SWIM_UNIT_ALIASES = {
    "meters": "meters", "meter": "meters", "metres": "meters", "metre": "meters", "m": "meters",
    "yards": "yards", "yard": "yards", "yds": "yards", "yd": "yards",
}
_SWIM_COURSES = (("meters", 25.0), ("meters", 50.0), ("yards", 25.0), ("yards", 50.0))
_SWIM_POOL_TOL_M = 0.05
# Common PR targets, each in its own course's unit.
SWIM_PR_TARGETS = {
    "meters": (25, 50, 100, 200, 250, 400, 800, 1000, 1500, 1900, 3800),
    "yards": (25, 50, 100, 200, 400, 500, 800, 1000, 1650),
}



def _swim_pr_candidates(splits, target, stroke_filter=None, unit="meters", pool_m=None):
    """Every valid exact-distance effort: continuous, one stroke, whole lengths.

    target is in `unit` ("meters" or "yards") and exactness is judged in that
    unit. The plausibility floor is always judged on the actual meters swum, so
    it means the same speed whichever unit the target is expressed in.
    """
    target = _num(target)
    unit_m = _SWIM_UNIT_M.get(unit)
    if target is None or target <= 0 or unit_m is None:
        return []

    wanted = str(stroke_filter).strip().lower() if stroke_filter else ""

    # Use the validated pool length instead of accumulating rounded Garmin
    # length distances. This prevents small rounding errors from hiding PRs.
    effective_pool_m = _num(pool_m)
    if effective_pool_m is None:
        effective_pool_m = _swim_recorded_pool_m(splits)

    out = []
    for run in _swim_pr_runs(_swim_pr_sequence(splits, effective_pool_m)):
        stroke = run[0]["stroke"]
        if wanted and wanted not in stroke.lower():
            continue

        target_m = target * unit_m

        for start in range(len(run)):
            total_t = 0.0

            for count, rec in enumerate(run[start:], start=1):
                total_t += rec["duration_s"]

                total_m = (
                    count * effective_pool_m
                    if effective_pool_m is not None
                    else sum(
                        item["distance_m"]
                        for item in run[start:start + count]
                    )
                )

                if total_m > target_m + _SWIM_PR_DISTANCE_TOL_M:
                    break

                if abs(total_m - target_m) <= _SWIM_PR_DISTANCE_TOL_M:
                    if _swim_pr_pace_ok(total_m, total_t):
                        out.append({
                            "time_seconds": total_t,
                            "pace_seconds_per_100_unit": (
                                total_t / target * 100.0
                            ),
                            "stroke": stroke,
                            "lengths": count,
                        })
                    break

    return out


def _best_swim_distance(splits, target_m, stroke_filter=None):
    """Fastest valid continuous swim effort of exactly target_m meters.

    Legacy metric entry point (response schema unchanged). It is course-agnostic:
    callers decide which sessions are eligible (see _swim_meter_legacy_ok).
    """
    best = None
    for candidate in _swim_pr_candidates(splits, target_m, stroke_filter):
        if best is None or candidate["time_seconds"] < best["time_seconds"]:
            best = candidate
    if best is None:
        return None
    return {
        "time_seconds": best["time_seconds"],
        "pace_seconds_per_100m": best["pace_seconds_per_100_unit"],
    }


def _swim_declared_course(pool_length):
    """Course named by the pool_length metadata (centimeters), or None."""
    cm = _num(pool_length)
    if cm is None or cm <= 0:
        return None
    pool_m = cm / 100.0
    for unit, size in _SWIM_COURSES:
        expected = size * _SWIM_UNIT_M[unit]
        if abs(pool_m - expected) <= _SWIM_POOL_TOL_M:
            return {"unit": unit, "pool_size": size, "pool_m": expected}
    return None


def _swim_recorded_pool_m(splits):
    """Most common recorded length distance (meters), or None."""
    counts = {}
    for lap in (splits or {}).get("lapDTOs", []) or []:
        for length in lap.get("lengthDTOs", []) or []:
            dist = _num(_first(length, "distance", "distanceMeters", "lengthDistance", "distanceInMeters"))
            dur = _num(_first(length, "duration", "durationSeconds", "lengthDuration"))
            if dist is None or dist <= 0 or dur is None or dur <= 0:
                continue
            counts[round(dist, 2)] = counts.get(round(dist, 2), 0) + 1
    return max(counts.items(), key=lambda item: item[1])[0] if counts else None


def _swim_course(pool_length, splits):
    """Validated course for one activity -> (course | None, reason)."""
    declared = _swim_declared_course(pool_length)
    if declared is None:
        return None, ("no_pool_length" if _num(pool_length) is None else "unsupported_pool_length")
    recorded = _swim_recorded_pool_m(splits)
    if recorded is None:
        return None, "no_length_records"
    if abs(recorded - declared["pool_m"]) > _SWIM_POOL_TOL_M:
        return None, "pool_length_conflicts_with_lengths"
    return declared, "ok"


def _swim_meter_legacy_ok(pool_length, splits):
    """Eligibility for the legacy meter query.

    Only verified meter courses qualify; a yard-course or conflicting session
    never does. A session with no pool metadata at all keeps working (as it did
    before courses existed) when its recorded lengths are a standard metric pool.
    """
    course, reason = _swim_course(pool_length, splits)
    if course is not None:
        return course["unit"] == "meters"
    if reason == "no_pool_length":
        recorded = _swim_recorded_pool_m(splits)
        return recorded is not None and any(abs(recorded - s) <= _SWIM_POOL_TOL_M for s in (25.0, 50.0))
    return False


def _best_swim_effort(splits, target, unit, stroke_filter, course):
    """Fastest valid effort of exactly `target` `unit`s on a validated course."""
    best = None
    for candidate in _swim_pr_candidates(splits, target, stroke_filter, unit, course["pool_m"]):
        if best is None or candidate["time_seconds"] < best["time_seconds"]:
            best = candidate
    return best


def _swim_pace_label(seconds, unit):
    n = int(round(seconds))
    return f"{n // 60}:{n % 60:02d}/100{_SWIM_UNIT_ABBR[unit]}"


def _swim_pr_row(unit, target, entry, swim_stroke):
    """One target's result. Distance and pace keys carry the course's own unit."""
    if entry is None:
        return {"target": target, "found": False}
    activity, effort, course = entry["activity"], entry["effort"], entry["course"]
    abbr = _SWIM_UNIT_ABBR[unit]
    pace = effort["pace_seconds_per_100_unit"]
    return {
        "target": target,
        "found": True,
        "activity_id": activity.activity_id,
        "date": str(activity.activity_date),
        "activity_name": activity.activity_name,
        "surface": _surface(activity, "swim"),
        "pace_source": "garmin_swim_lengths",
        "pool_length": course["pool_size"],
        "pool_length_unit": unit,
        f"distance_{unit}": target,
        "time_seconds": round(effort["time_seconds"], 2),
        f"pace_seconds_per_100{abbr}": round(pace, 2),
        f"pace_per_100{abbr}": _swim_pace_label(pace, unit),
        "stroke": effort["stroke"],
        "stroke_filter": swim_stroke,
    }


def get_best_swim_performance(
    unit: str = "yards",
    target: float | None = None,
    window_days: int = 30,
    swim_stroke: str | None = None,
    period: str | None = None,
):
    """Best exact swim efforts, calculated and reported in the pool's own unit.

    Only sessions whose course is verified (see _swim_course) and is in the
    requested unit are searched, so a yard effort is never reported or compared
    as a meter effort. target=None searches the common targets for the unit.
    """
    unit = _SWIM_UNIT_ALIASES.get(str(unit or "").strip().lower())
    if unit is None:
        return {"error": "unit must be yards or meters"}
    if target is None:
        targets = SWIM_PR_TARGETS[unit]
    else:
        value = _num(target)
        if value is None or value <= 0:
            return {"error": "target must be greater than zero"}
        targets = (value,)

    period_start, period_end = _period_bounds(window_days, period)
    base = {
        "sport": "swim",
        "course_unit": unit,
        "target_units": unit,
        "window_days": window_days,
        "period": period,
        "period_start": str(period_start),
        "period_end": str(period_end),
    }
    activities = _activity_query("swim", window_days, period)
    if not activities:
        return {**base, "found": False, "results": [], "reason": "No activities in requested period."}

    g = get_garmin_client()
    best = {t: None for t in targets}
    in_course = other_unit = 0
    unclassified = {}
    errors = []
    for activity in activities:
        try:
            splits = g.get_activity_splits(activity.activity_id)
            course, reason = _swim_course(getattr(activity, "pool_length", None), splits)
            if course is None:
                unclassified[reason] = unclassified.get(reason, 0) + 1
                continue
            if course["unit"] != unit:
                other_unit += 1
                continue
            in_course += 1
            for t in targets:
                effort = _best_swim_effort(splits, t, unit, swim_stroke, course)
                if effort and (best[t] is None or effort["time_seconds"] < best[t]["effort"]["time_seconds"]):
                    best[t] = {"activity": activity, "effort": effort, "course": course}
        except Exception as exc:
            errors.append({"activity_id": activity.activity_id, "error": str(exc)})

    rows = [_swim_pr_row(unit, t, best[t], swim_stroke) for t in targets]
    out = {
        **base,
        "found": any(row["found"] for row in rows),
        "activities_considered": len(activities),
        "activities_in_course": in_course,
        "activities_excluded": {"other_course_unit": other_unit, "unclassified": unclassified},
        "results": rows,
    }
    if errors:
        out["errors"] = errors[-5:]
    return out

def _manual_treadmill_intervals(activity_id: int):
    try:
        from coaching_tables import get_treadmill_intervals
        saved = get_treadmill_intervals(activity_id) or {}
        rows = saved.get("manual_treadmill_intervals") if isinstance(saved, dict) else saved
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def _surface(activity, sport: str) -> str:
    """Classify surface from Garmin activity type first, then name."""
    activity_type = str(getattr(activity, "activity_type", "") or "").lower()
    activity_name = str(getattr(activity, "activity_name", "") or "").lower()
    kind = activity_type.replace(" ", "_")
    name = activity_name.replace("-", " ").replace("_", " ")

    # Prefer structured Garmin activity type over the display name.
    if sport == "run":
        if "treadmill" in kind:
            return "treadmill"
        if any(term in kind for term in ("indoor_running", "virtual_run")):
            return "indoor"
        if any(term in name for term in ("treadmill", "tread mill")):
            return "treadmill"
        if any(term in name for term in ("indoor run", "virtual run")):
            return "indoor"
        if any(term in kind for term in ("running", "trail_running")):
            return "outdoor"
        if any(term in name for term in ("running", "outdoor run", "trail run")):
            return "outdoor"

    elif sport == "bike":
        if any(term in kind for term in (
            "indoor_cycling", "virtual_cycling",
            "indoor_biking", "stationary_biking",
        )):
            return "indoor"
        if any(term in name for term in (
            "indoor cycling", "indoor bike", "trainer ride", "virtual ride",
        )):
            return "indoor"
        if any(term in kind for term in (
            "cycling", "road_cycling", "mountain_biking",
        )):
            return "outdoor"
        if any(term in name for term in (
            "cycling", "outdoor ride", "road ride",
        )):
            return "outdoor"

    elif sport == "swim":
        if any(term in kind for term in ("lap_swimming", "pool_swimming")):
            return "pool"
        if "open_water" in kind:
            return "open_water"
        if "pool" in name:
            return "pool"
        if "open water" in name:
            return "open_water"

    return "unknown"


def _manual_pace(row):
    if not isinstance(row, dict):
        return None
    for key in ("pace", "manual_pace", "target_pace", "pace_per_mile", "pace_per_mi", "actual_pace", "reported_pace"):
        value = row.get(key)
        if value is not None and str(value).strip():
            value = str(value).strip()
            if ":" in value:
                parts = value.replace("/mi", "").strip().split(":")
                if len(parts) == 2:
                    try:
                        return float(parts[0]) * 60 + float(parts[1])
                    except ValueError:
                        pass
            try:
                return float(value)
            except ValueError:
                pass
    return None


def _manual_interval_seconds(row):
    if not isinstance(row, dict):
        return None
    for key in ("duration_seconds", "duration", "seconds", "elapsed_seconds"):
        value = _num(row.get(key))
        if value and value > 0:
            return value
    start = row.get("start_time") or row.get("start")
    end = row.get("end_time") or row.get("end")
    try:
        if start is not None and end is not None:
            a = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
            b = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
            return max(0.0, (b - a).total_seconds())
    except Exception:
        pass
    return None


def _manual_run_effort(rows, target_m):
    """Best treadmill effort from manually recorded pace/duration intervals."""
    if not rows or target_m <= 0:
        return None
    best = None
    for start in range(len(rows)):
        total_distance = 0.0
        total_time = 0.0
        for i in range(start, len(rows)):
            pace = _manual_pace(rows[i])
            duration = _manual_interval_seconds(rows[i])
            if pace is None or pace <= 0 or duration is None or duration <= 0:
                break
            distance = duration / pace * 1609.344
            total_distance += distance
            total_time += duration
            if total_distance < target_m:
                continue
            # Interpolate the final interval when only part of it is needed.
            excess = total_distance - target_m
            if excess > 0:
                fraction = 1.0 - excess / distance
                if fraction < 0.25:
                    break
                total_time -= duration * excess / distance
            pace_target = total_time / target_m * 1609.344
            candidate = {
                "time_seconds": total_time,
                "pace_seconds_per_mile": pace_target,
                "pace_source": "manual_treadmill",
            }
            if best is None or candidate["time_seconds"] < best["time_seconds"]:
                best = candidate
            break
    return best


_INDOOR_BIKE_TYPE_KEYS = {
    "indoor_cycling",
    "virtual_ride",
    "indoor_biking",
    "stationary_biking",
    "virtual_cycling",
}
_OUTDOOR_BIKE_TYPE_KEYS = {
    "cycling",
    "road_biking",
    "mountain_biking",
    "gravel_cycling",
}
_TREADMILL_TYPE_KEYS = {
    "treadmill_running",
    "indoor_running",
    "virtual_run",
}
_OUTDOOR_RUN_TYPE_KEYS = {"running", "trail_running"}
_POOL_SWIM_TYPE_KEYS = {"lap_swimming", "pool_swimming"}
_OPEN_WATER_SWIM_TYPE_KEYS = {"open_water_swimming"}


def _garmin_type_key(activity) -> str:
    raw = getattr(activity, "raw_data", None)
    if raw:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, dict):
                activity_type = data.get("activityType")
                if isinstance(activity_type, dict):
                    key = activity_type.get("typeKey")
                    if key:
                        return str(key).lower()
        except (TypeError, ValueError, AttributeError):
            pass

    return str(getattr(activity, "activity_type", "") or "").lower()


def _surface(activity, sport: str, treadmill: bool = False) -> str:
    key = _garmin_type_key(activity)

    if sport == "run":
        if treadmill or key in _TREADMILL_TYPE_KEYS:
            return "treadmill"
        if key in _OUTDOOR_RUN_TYPE_KEYS:
            return "outdoor"
        return "unknown"

    if sport == "bike":
        if key in _INDOOR_BIKE_TYPE_KEYS:
            return "indoor"
        if key in _OUTDOOR_BIKE_TYPE_KEYS:
            return "outdoor"
        return "unknown"

    if sport == "swim":
        if key in _POOL_SWIM_TYPE_KEYS:
            return "pool"
        if key in _OPEN_WATER_SWIM_TYPE_KEYS:
            return "open_water"
        return "unknown"

    return "unknown"


def get_best_performance(
    sport: str,
    target: float,
    metric: str = "auto",
    window_days: int = 30,
    swim_stroke: str | None = None,
    period: str | None = None,
):
    sport = sport.lower().strip()

    if sport not in SPORTS:
        return {"error": "sport must be run, bike, or swim"}

    target = _num(target)
    if target is None or target <= 0:
        return {"error": "target must be greater than zero"}

    # Explicit all-time aliases and window_days=None both mean all history.
    # The default window_days=30 remains unchanged for existing callers.
    normalized_period = (period or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized_period in {"all", "all_time", "alltime", "ever", "lifetime", "entire_history"}:
        period = "all_time"
        window_days = None
    elif window_days is None and not normalized_period:
        period = "all_time"

    metric = (
        "duration"
        if metric == "auto" and sport == "bike"
        else ("distance" if metric == "auto" else metric)
    )

    if metric not in {"distance", "duration"}:
        return {"error": "metric must be auto, distance, or duration"}

    if sport != "bike" and metric != "distance":
        return {"error": "run and swim use distance in meters"}

    if sport == "bike" and metric != "duration":
        return {"error": "bike uses duration in seconds"}

    activities = _activity_query(sport, window_days, period)

    if not activities:
        return {
            "sport": sport,
            "target": target,
            "found": False,
            "period": period,
            "reason": "No activities in requested period.",
        }

    g = get_garmin_client()
    best = None
    errors = []

    for activity in activities:
        try:
            treadmill = sport == "run" and _is_treadmill(activity)

            if sport == "swim":
                splits = g.get_activity_splits(activity.activity_id)
                # Meter query: never use a yard-course (or unverifiable) session.
                if not _swim_meter_legacy_ok(getattr(activity, "pool_length", None), splits):
                    continue
                result = _best_swim_distance(splits, target, swim_stroke)
                source = "garmin_swim_lengths"

            elif sport == "run" and treadmill:
                result = _manual_run_effort(
                    _manual_treadmill_intervals(activity.activity_id),
                    target,
                )
                source = "manual_treadmill" if result else None

            else:
                samples = _detail_samples(
                    g.get_activity_details(activity.activity_id),
                    sport,
                )

                result = (
                    _distance_effort(samples, target)
                    if sport == "run"
                    else _duration_effort(samples, target, "power")
                )

                source = "garmin_detail_samples"

            if not result:
                continue

            # Select the best result across all activities.
            if sport == "bike":
                better = (
                    best is None
                    or result["value"] > best["result"]["value"]
                )
            else:
                better = (
                    best is None
                    or result["time_seconds"]
                    < best["result"]["time_seconds"]
                )

            if better:
                best = {
                    "activity": activity,
                    "result": result,
                    "source": source,
                    "surface": _surface(activity, sport, treadmill),
                }

        except Exception as exc:
            errors.append(
                {
                    "activity_id": activity.activity_id,
                    "error": str(exc),
                }
            )

    if best is None:
        return {
            "sport": sport,
            "target": target,
            "found": False,
            "period": period,
            "errors": errors[-5:],
        }

    activity = best["activity"]
    result = best["result"]

    period_start, period_end = _period_bounds(window_days, period)

    reported_period_start = (
        min((a.activity_date for a in activities if getattr(a, "activity_date", None)), default=None)
        if period == "all_time"
        else period_start
    )

    out = {
        "sport": sport,
        "target": target,
        "target_units": "seconds" if sport == "bike" else "meters",
        "window_days": window_days,
        "period": period,
        "period_start": str(reported_period_start) if reported_period_start else None,
        "period_end": str(period_end),
        "found": True,
        "activity_id": activity.activity_id,
        "date": str(activity.activity_date),
        "activity_name": activity.activity_name,
        "surface": best["surface"],
        "pace_source": result.get("pace_source", best["source"]),
    }
    if sport == "bike":
        out.update(
            {
                "duration_seconds": target,
                "best_power_w": round(result["value"], 1),
                "timer_basis": result.get("timer_basis"),
                "elapsed_time_seconds": (
                    round(result["elapsed_time_seconds"], 2)
                    if result.get("elapsed_time_seconds") is not None
                    else None
                ),
                "moving_time_seconds": (
                    round(result["moving_time_seconds"], 2)
                    if result.get("moving_time_seconds") is not None
                    else None
                ),
                "pause_seconds": (
                    round(result["pause_seconds"], 2)
                    if result.get("pause_seconds") is not None
                    else None
                ),
                "window_start": (
                    _coerce_timestamp(
                        result.get("start_timestamp")
                    ).isoformat()
                    if result.get("start_timestamp")
                    else None
                ),
                "window_end": (
                    _coerce_timestamp(
                        result.get("end_timestamp")
                    ).isoformat()
                    if result.get("end_timestamp")
                    else None
                ),
                "moving_counter_consistent": result.get(
                    "moving_counter_consistent"
                ),
                "data_quality": (
                    "high"
                    if result.get("moving_counter_consistent") is not False
                    else "medium"
                ),
            }
        )

    elif sport == "run":
        out.update(
            {
                "distance_m": target,
                "time_seconds": round(result["time_seconds"], 2),
                "pace_per_mile": _pace_from_seconds_per_mile(
                    result["pace_seconds_per_mile"]
                ),
                "timer_basis": result.get("timer_basis"),
                "elapsed_time_seconds": (
                    round(result["elapsed_time_seconds"], 2)
                    if result.get("elapsed_time_seconds") is not None
                    else None
                ),
                "moving_time_seconds": (
                    round(result["moving_time_seconds"], 2)
                    if result.get("moving_time_seconds") is not None
                    else None
                ),
                "pause_seconds": (
                    round(result["pause_seconds"], 2)
                    if result.get("pause_seconds") is not None
                    else None
                ),
                "window_start": (
                    _coerce_timestamp(
                        result.get("start_timestamp")
                    ).isoformat()
                    if result.get("start_timestamp")
                    else None
                ),
                "window_end": (
                    _coerce_timestamp(
                        result.get("end_timestamp")
                    ).isoformat()
                    if result.get("end_timestamp")
                    else None
                ),
                "moving_counter_consistent": result.get(
                    "moving_counter_consistent"
                ),
                "data_quality": result.get("data_quality"),
            }
        )

    else:
        out.update(
            {
                "distance_m": target,
                "time_seconds": round(result["time_seconds"], 2),
                "pace_per_100m": _pace_from_seconds_per_100m(
                    result["pace_seconds_per_100m"]
                ),
                "stroke_filter": swim_stroke,
            }
        )

    if errors:
        out["errors"] = errors[-5:]

    return out

def _load_zone_config():
    initialize_database()
    session = get_session()
    try:
        profile = session.query(AthleteProfile).filter_by(id=1).first()
        raw = getattr(profile, "training_zones_json", None) if profile else None
        return json.loads(raw) if raw else {}
    except Exception:
        return {}
    finally:
        session.close()


def set_training_zones(config: dict) -> dict:
    if not isinstance(config, dict):
        return {"error": "config must be a dictionary"}
    initialize_database()
    session = get_session()
    try:
        profile = session.query(AthleteProfile).filter_by(id=1).first()
        if not profile:
            profile = AthleteProfile(id=1)
            session.add(profile)
        profile.training_zones_json = json.dumps(config)
        session.commit()
        return {"success": True, "training_zones": config}
    finally:
        session.close()


def _zone_threshold(config, sport, zone):
    sport_cfg = config.get(sport, {}) if isinstance(config, dict) else {}
    return sport_cfg.get(str(zone), {}) if isinstance(sport_cfg, dict) else {}


def _in_range(value, low, high):
    value = _num(value)
    if value is None:
        return False
    low = _num(low)
    high = _num(high)
    if low is None and high is None:
        return False
    if low is not None and value < low:
        return False
    if high is not None and value > high:
        return False
    return True


def _classify_sample(sample, threshold, sport):
    hr = sample.get("hr")
    hr_ok = _in_range(hr, threshold.get("hr_bpm_min"), threshold.get("hr_bpm_max")) if sport in {"run", "bike"} else False
    if sport == "run":
        pace = sample.get("pace_sec_per_mile")
        metric_ok = _in_range(pace, threshold.get("pace_sec_per_mile_min"), threshold.get("pace_sec_per_mile_max"))
    elif sport == "bike":
        metric_ok = _in_range(sample.get("power"), threshold.get("power_w_min"), threshold.get("power_w_max"))
    else:
        metric_ok = _in_range(sample.get("pace_sec_per_100m"), threshold.get("pace_sec_per_100m_min"), threshold.get("pace_sec_per_100m_max"))
    if sport == "swim":
        return False, False, metric_ok
    return hr_ok or metric_ok, hr_ok, metric_ok


def _time_in_zone_samples(samples, threshold, sport):
    """Return HR-only, metric-only, both, and exact union time from samples."""
    hr_seconds = metric_seconds = both_seconds = union_seconds = 0.0
    for a, b in zip(samples, samples[1:]):
        dt = (b["t"] - a["t"]).total_seconds()
        if dt <= 0 or dt > 10:
            continue
        _, hr_ok, metric_ok = _classify_sample(b, threshold, sport)
        if hr_ok:
            hr_seconds += dt
        if metric_ok:
            metric_seconds += dt
        if hr_ok and metric_ok:
            both_seconds += dt
        if hr_ok or metric_ok:
            union_seconds += dt
    return union_seconds, hr_seconds, metric_seconds, both_seconds


def _sample_series(details, sport):
    samples = _detail_samples(details, sport)
    for sample in samples:
        if sport == "run":
            speed = sample.get("speed")
            sample["pace_sec_per_mile"] = 1609.344 / speed if speed and speed > 0 else None
        elif sport == "bike":
            sample["pace_sec_per_mile"] = None
    return samples


def _manual_zone_time(activity_id, threshold):
    total = 0.0
    for row in _manual_treadmill_intervals(activity_id):
        pace = _manual_pace(row)
        duration = _manual_interval_seconds(row)
        if pace is not None and duration is not None and _in_range(pace, threshold.get("pace_sec_per_mile_min"), threshold.get("pace_sec_per_mile_max")):
            total += duration
    return total


def _zone_result(sport, zone, window_days, period, threshold, combined, hr_only, metric_only, both, activity_count, errors):
    result = {
        "sport": sport, "zone": zone, "window_days": window_days, "period": period,
        "period_start": str(_period_bounds(window_days, period)[0]),
        "period_end": str(_period_bounds(window_days, period)[1]),
        "thresholds": threshold,
        "combined_or_seconds": round(combined, 1),
        "combined_or_hours": round(combined / 3600, 3),
        "activity_count": activity_count,
        "breakdown": {},
        "notes": [
            "Run classification uses HR OR pace.",
            "Bike classification uses HR OR power.",
            "Swim classification uses pace only.",
            "Treadmill run pace uses manually reported treadmill pace; Garmin treadmill pace is reference-only.",
            "Zone bounds are inclusive; null is an open bound.",
        ],
        "errors": errors[-5:],
    }
    if sport in {"run", "bike"}:
        result["breakdown"] = {
            "hr_seconds": round(hr_only, 1),
            "metric_seconds": round(metric_only, 1),
            "both_seconds": round(both, 1),
            "combined_or_seconds": round(combined, 1),
        }
    else:
        result["breakdown"] = {
            "pace_seconds": round(metric_only, 1),
            "combined_or_seconds": round(combined, 1),
        }
    return result


def _get_one_zone(sport, zone, window_days, period, config, activities=None, g=None):
    threshold = _zone_threshold(config, sport, zone)
    if not threshold:
        return {"error": f"No thresholds configured for {sport} zone {zone}. Use set_training_zones first.", "sport": sport, "zone": zone}
    activities = _activity_query(sport, window_days, period) if activities is None else activities
    g = get_garmin_client() if g is None else g
    combined = hr_only = metric_only = both = 0.0
    activity_count = 0
    errors = []
    for activity in activities:
        try:
            treadmill = sport == "run" and _is_treadmill(activity)
            if sport == "swim":
                activity_time = 0.0
                for item in _swim_lengths(g.get_activity_splits(activity.activity_id)):
                    pace100 = item["duration_s"] / item["distance_m"] * 100.0
                    if _in_range(pace100, threshold.get("pace_sec_per_100m_min"), threshold.get("pace_sec_per_100m_max")):
                        activity_time += item["duration_s"]
                combined += activity_time
                metric_only += activity_time
                if activity_time:
                    activity_count += 1
                continue

            samples = _sample_series(g.get_activity_details(activity.activity_id), sport)
            if treadmill:
                # Manual pace has no reliable timestamp alignment with Garmin HR
                # in the saved annotation format, so do not fabricate an AND/OR
                # intersection. Report each clock separately and use the larger
                # clock as the conservative union estimate.
                manual_time = _manual_zone_time(activity.activity_id, threshold)
                _, h, _, _ = _time_in_zone_samples(
                    samples,
                    {"hr_bpm_min": threshold.get("hr_bpm_min"), "hr_bpm_max": threshold.get("hr_bpm_max")},
                    sport,
                )
                hr_only += h
                metric_only += manual_time
                combined += max(h, manual_time)
                if h or manual_time:
                    activity_count += 1
                errors.append({"activity_id": activity.activity_id, "warning": "Treadmill HR/HR+manual-pace overlap cannot be timestamp-exact without manual interval timestamps; combined_or_seconds uses max(HR, manual-pace) rather than double-counting."})
                continue

            c, h, m, b = _time_in_zone_samples(samples, threshold, sport)
            combined += c
            hr_only += h
            metric_only += m
            both += b
            if c:
                activity_count += 1
        except Exception as exc:
            errors.append({"activity_id": activity.activity_id, "error": str(exc)})
    return _zone_result(sport, zone, window_days, period, threshold, combined, hr_only, metric_only, both, activity_count, errors)


def get_time_in_zone(sport: str, zone: int | str = 3, window_days: int = 7, period: str | None = None):
    sport = sport.lower().strip()
    if sport not in SPORTS:
        return {"error": "sport must be bike, run, or swim"}
    config = _load_zone_config()
    if str(zone).lower() == "all":
        activities = _activity_query(sport, window_days, period)
        g = get_garmin_client()
        zones = [_get_one_zone(sport, z, window_days, period, config, activities, g) for z in range(1, 7)]
        return {
            "sport": sport, "zone": "all", "window_days": window_days, "period": period,
            "period_start": str(_period_bounds(window_days, period)[0]),
            "period_end": str(_period_bounds(window_days, period)[1]),
            "zones": zones,
        }
    try:
        zone_int = int(zone)
    except (TypeError, ValueError):
        return {"error": "zone must be 1-6 or 'all'"}
    if zone_int < 1 or zone_int > 6:
        return {"error": "zone must be 1-6 or 'all'"}
    return _get_one_zone(sport, zone_int, window_days, period, config)
