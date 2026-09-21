from __future__ import annotations

from datetime import datetime
from statistics import mean, stdev
from typing import Any


# ============================================================
# Generic helpers
# ============================================================

def _clean(values):
    return [
        v for v in values
        if v is not None and isinstance(v, (int, float))
    ]


def _avg(values):
    values = _clean(values)
    return round(mean(values), 2) if values else None


def _minimum(values):
    values = _clean(values)
    return min(values) if values else None


def _maximum(values):
    values = _clean(values)
    return max(values) if values else None


def _first(values):
    return values[0] if values else None


def _last(values):
    return values[-1] if values else None


def _change(first, last):
    if first is None or last is None:
        return None
    return round(last - first, 2)


def _percent_change(first, last):
    if first in (None, 0) or last is None:
        return None

    return round(((last - first) / first) * 100, 2)


def _cv(values):
    values = _clean(values)

    if len(values) < 2:
        return None

    avg = mean(values)

    if avg == 0:
        return None

    return round(stdev(values) / avg * 100, 2)


def _safe_float(value):
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value, digits=2):
    if value is None:
        return None

    try:
        return round(value, digits)
    except (TypeError, ValueError):
        return value


def _duration_seconds(value):
    """
    Garmin durations are normally already numeric seconds.
    """
    return _safe_float(value)


def _pace_per_100m(distance_m, duration_seconds):
    """
    Return seconds per 100m.
    """
    if not distance_m or not duration_seconds:
        return None

    return round(duration_seconds / distance_m * 100, 2)


def _format_time(seconds):
    if seconds is None:
        return None

    seconds = float(seconds)

    minutes = int(seconds // 60)
    remaining = seconds - minutes * 60

    if minutes:
        return f"{minutes}:{remaining:04.1f}"

    return f"0:{remaining:04.1f}"


def _format_pace(seconds):
    if seconds is None:
        return None

    minutes = int(seconds // 60)
    remaining = seconds - minutes * 60

    return f"{minutes}:{remaining:04.1f}"


# ============================================================
# Activity-detail sample preparation
# ============================================================

def _prepare_samples(samples):
    """
    Convert parsed activity-detail samples into elapsed-time samples.

    Expected parsed sample format:

    {
        "timestamp": ...,
        "heart_rate": ...,
        "power": ...,
        ...
    }
    """

    if not samples:
        return []

    prepared = []

    first_timestamp = None

    for sample in samples:

        timestamp = (
            sample.get("timestamp")
            or sample.get("timestamp_ms")
            or sample.get("time")
        )

        if timestamp is None:
            continue

        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                ).timestamp() * 1000
            except ValueError:
                continue

        try:
            timestamp = float(timestamp)
        except (TypeError, ValueError):
            continue

        if first_timestamp is None:
            first_timestamp = timestamp

        prepared_sample = dict(sample)

        prepared_sample["elapsed_seconds"] = (
            timestamp - first_timestamp
        ) / 1000

        prepared.append(prepared_sample)

    return prepared


# ============================================================
# Garmin lap helpers
# ============================================================

def _lap_duration(lap):
    return _safe_float(lap.get("duration"))


def _lap_elapsed_duration(lap):
    return _safe_float(lap.get("elapsedDuration"))


def _lap_distance(lap):
    return _safe_float(lap.get("distance"))


def _lap_type(lap):
    intensity = lap.get("intensityType")

    if intensity:
        return str(intensity).lower()

    return ""


def _lap_stroke(lap):
    """
    Garmin swim payloads may expose swim type under different keys.
    """

    for key in (
        "swimStroke",
        "strokeType",
        "stroke",
        "activityName",
        "name",
    ):
        value = lap.get(key)

        if value:
            return str(value)

    return None


def _is_rest_lap(lap):
    """
    Garmin swim Rest laps have zero distance.
    """

    distance = _lap_distance(lap)

    if distance == 0:
        return True

    stroke = _lap_stroke(lap)

    if stroke and stroke.lower() == "rest":
        return True

    return False


def _lap_metric(lap, *keys):
    for key in keys:
        if key in lap and lap[key] is not None:
            return lap[key]

    return None


def _lap_start_time(lap):
    return lap.get("startTimeGMT") or lap.get("startTimeLocal")


# ============================================================
# Bike metrics
# ============================================================

def _bike_metrics(lap):
    return {
        "duration_seconds": _round(
            _lap_duration(lap)
        ),

        "elapsed_duration_seconds": _round(
            _lap_elapsed_duration(lap)
        ),

        "distance_m": _round(
            _lap_distance(lap)
        ),

        "avg_power": _round(
            _lap_metric(
                lap,
                "averagePower",
                "avgPower",
            )
        ),

        "normalized_power": _round(
            _lap_metric(
                lap,
                "normalizedPower",
                "normPower",
            )
        ),

        "max_power": _round(
            _lap_metric(
                lap,
                "maxPower",
            )
        ),

        "min_power": _round(
            _lap_metric(
                lap,
                "minPower",
            )
        ),

        "total_work_kj": _round(
            _lap_metric(
                lap,
                "totalWork",
            )
        ),

        "avg_hr": _round(
            _lap_metric(
                lap,
                "averageHR",
                "avgHR",
            )
        ),

        "max_hr": _round(
            _lap_metric(
                lap,
                "maxHR",
            )
        ),

        "avg_cadence": _round(
            _lap_metric(
                lap,
                "averageBikeCadence",
                "averageBikingCadenceInRevPerMinute",
                "avgCadence",
            )
        ),

        "max_cadence": _round(
            _lap_metric(
                lap,
                "maxBikeCadence",
                "maxBikingCadenceInRevPerMinute",
                "maxCadence",
            )
        ),

        "avg_speed": _round(
            _lap_metric(
                lap,
                "averageSpeed",
                "avgSpeed",
            )
        ),

        "calories": _round(
            _lap_metric(
                lap,
                "calories",
            )
        ),
    }


# ============================================================
# Run metrics
# ============================================================

def _run_metrics(lap):
    return {
        "duration_seconds": _round(
            _lap_duration(lap)
        ),

        "elapsed_duration_seconds": _round(
            _lap_elapsed_duration(lap)
        ),

        "distance_m": _round(
            _lap_distance(lap)
        ),

        "avg_speed": _round(
            _lap_metric(
                lap,
                "averageSpeed",
                "avgSpeed",
            )
        ),

        "max_speed": _round(
            _lap_metric(
                lap,
                "maxSpeed",
            )
        ),

        "avg_hr": _round(
            _lap_metric(
                lap,
                "averageHR",
                "avgHR",
            )
        ),

        "max_hr": _round(
            _lap_metric(
                lap,
                "maxHR",
            )
        ),

        "avg_power": _round(
            _lap_metric(
                lap,
                "averagePower",
                "avgPower",
                "averageRunningPower",
                "avgRunningPower",
                "runningPower",
            )
        ),

        "max_power": _round(
            _lap_metric(
                lap,
                "maxPower",
            )
        ),

        "avg_cadence": _round(
            _lap_metric(
                lap,
                "averageRunCadence",
                "averageRunningCadence",
                "avgRunningCadence",
            )
        ),

        "max_cadence": _round(
            _lap_metric(
                lap,
                "maxRunCadence",
                "maxRunningCadence",
                "maxRunningCadenceInStepsPerMinute",
            )
        ),

        "stride_length": _round(
            _lap_metric(
                lap,
                "avgStrideLength",
                "averageStrideLength",
                "strideLength",
            )
        ),

        "vertical_oscillation": _round(
            _lap_metric(
                lap,
                "avgVerticalOscillation",
                "averageVerticalOscillation",
                "verticalOscillation",
            )
        ),

        "vertical_ratio": _round(
            _lap_metric(
                lap,
                "avgVerticalRatio",
                "averageVerticalRatio",
                "verticalRatio",
            )
        ),

        "ground_contact_time": _round(
            _lap_metric(
                lap,
                "avgGroundContactTime",
                "averageGroundContactTime",
                "groundContactTime",
            )
        ),
    }


# ============================================================
# SWIM metrics
# ============================================================

def _swim_metrics(lap):
    """
    Garmin-native swim lap analysis.

    This deliberately treats Garmin swim laps as the primary
    source of truth rather than attempting to reconstruct
    intervals from raw HR/time-series samples.
    """

    duration = _lap_duration(lap)
    distance = _lap_distance(lap)

    pace = _pace_per_100m(
        distance,
        duration,
    )

    return {
        # -------------------------
        # Basic structure
        # -------------------------

        "duration_seconds": _round(
            duration
        ),

        "elapsed_duration_seconds": _round(
            _lap_elapsed_duration(lap)
        ),

        "distance_m": _round(
            distance
        ),

        "lengths": _lap_metric(
            lap,
            "lengths",
            "totalLengths",
        ),

        "stroke_type": _lap_stroke(lap),

        # -------------------------
        # Pace
        # -------------------------

        "pace_seconds_per_100m": _round(
            pace
        ),

        "pace_per_100m": _format_pace(
            pace
        ),

        # Garmin often provides these directly
        "average_pace": _lap_metric(
            lap,
            "averagePace",
            "averagePaceString",
        ),

        "moving_pace": _lap_metric(
            lap,
            "movingPace",
            "movingPaceString",
        ),

        # -------------------------
        # Heart rate
        # -------------------------

        "avg_hr": _round(
            _lap_metric(
                lap,
                "averageHR",
                "avgHR",
            )
        ),

        "max_hr": _round(
            _lap_metric(
                lap,
                "maxHR",
            )
        ),

        # -------------------------
        # Stroke metrics
        # -------------------------

        "stroke_count": _round(
            _lap_metric(
                lap,
                "totalNumberOfStrokes",
                "strokes",
                "strokeCount",
            )
        ),

        "avg_stroke_rate": _round(
            _lap_metric(
                lap,
                "averageStrokeRate",
                "avgStrokeRate",
            )
        ),

        "max_stroke_rate": _round(
            _lap_metric(
                lap,
                "maxStrokeRate",
            )
        ),

        # -------------------------
        # Efficiency
        # -------------------------

        "avg_swolf": _round(
            _lap_metric(
                lap,
                "averageSwolf",
                "avgSwolf",
            )
        ),

        # -------------------------
        # Calories
        # -------------------------

        "calories": _round(
            _lap_metric(
                lap,
                "calories",
            )
        ),
    }


# ============================================================
# Generic lap metrics
# ============================================================

def _metrics_for_sport(lap, sport):
    sport = sport.lower()

    if sport == "bike":
        return _bike_metrics(lap)

    if sport == "run":
        return _run_metrics(lap)

    if sport == "swim":
        return _swim_metrics(lap)

    return {
        "duration_seconds": _round(
            _lap_duration(lap)
        ),
        "distance_m": _round(
            _lap_distance(lap)
        ),
        "avg_hr": _round(
            _lap_metric(lap, "averageHR", "avgHR")
        ),
        "max_hr": _round(
            _lap_metric(lap, "maxHR")
        ),
    }


# ============================================================
# Swim analysis
# ============================================================

def _analyze_swim_laps(laps):
    """
    Convert Garmin swim laps into a compact structured workout.

    Every Garmin swim lap is preserved as either:

        SWIM
        DRILL
        REST
        OTHER

    Rest is never treated as a swimming repetition.
    """

    segments = []

    for index, lap in enumerate(laps, start=1):

        distance = _lap_distance(lap)
        duration = _lap_duration(lap)

        stroke = _lap_stroke(lap)

        if _is_rest_lap(lap):

            segments.append({
                "type": "REST",
                "lap_index": index,
                "duration_seconds": _round(duration),
                "duration": _format_time(duration),
            })

            continue

        stroke_lower = (
            stroke.lower()
            if stroke
            else ""
        )

        if "drill" in stroke_lower:
            segment_type = "DRILL"

        elif distance and distance > 0:
            segment_type = "SWIM"

        else:
            segment_type = "OTHER"

        metrics = _swim_metrics(lap)

        segments.append({
            "type": segment_type,
            "lap_index": index,
            "metrics": metrics,
        })

    # --------------------------------------------------------
    # Group swim work with following recovery
    # --------------------------------------------------------

    reps = []

    for i, segment in enumerate(segments):

        if segment["type"] not in {
            "SWIM",
            "DRILL",
        }:
            continue

        rest_after = None

        if i + 1 < len(segments):
            next_segment = segments[i + 1]

            if next_segment["type"] == "REST":
                rest_after = next_segment

        rep = {
            "rep": len(reps) + 1,
            "type": segment["type"],
            "lap_index": segment["lap_index"],
            "metrics": segment["metrics"],
        }

        if rest_after:
            rep["recovery"] = {
                "lap_index": rest_after["lap_index"],
                "duration_seconds": rest_after[
                    "duration_seconds"
                ],
                "duration": rest_after[
                    "duration"
                ],
            }

        reps.append(rep)

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    swim_reps = [
        r for r in reps
        if r["type"] == "SWIM"
    ]

    drill_reps = [
        r for r in reps
        if r["type"] == "DRILL"
    ]

    distances = [
        r["metrics"]["distance_m"]
        for r in swim_reps
        if r["metrics"].get("distance_m") is not None
    ]

    durations = [
        r["metrics"]["duration_seconds"]
        for r in swim_reps
        if r["metrics"].get("duration_seconds") is not None
    ]

    paces = [
        r["metrics"]["pace_seconds_per_100m"]
        for r in swim_reps
        if r["metrics"].get(
            "pace_seconds_per_100m"
        ) is not None
    ]

    hrs = [
        r["metrics"]["avg_hr"]
        for r in swim_reps
        if r["metrics"].get("avg_hr") is not None
    ]

    swolfs = [
        r["metrics"]["avg_swolf"]
        for r in swim_reps
        if r["metrics"].get("avg_swolf") is not None
    ]

    stroke_rates = [
        r["metrics"]["avg_stroke_rate"]
        for r in swim_reps
        if r["metrics"].get("avg_stroke_rate") is not None
    ]

    stroke_counts = [
        r["metrics"]["stroke_count"]
        for r in swim_reps
        if r["metrics"].get("stroke_count") is not None
    ]

    return {
        "sport": "swim",

        "reps": reps,

        "summary": {
            "total_work_reps": len(swim_reps),
            "total_drill_reps": len(drill_reps),

            "total_work_distance_m": (
                round(sum(distances), 2)
                if distances
                else 0
            ),

            "total_work_time_seconds": (
                round(sum(durations), 2)
                if durations
                else 0
            ),

            "avg_rep_distance_m": _avg(distances),

            "avg_rep_duration_seconds": _avg(
                durations
            ),

            "avg_pace_seconds_per_100m": _avg(
                paces
            ),

            "avg_hr": _avg(hrs),

            "avg_swolf": _avg(swolfs),

            "avg_stroke_rate": _avg(
                stroke_rates
            ),

            "avg_stroke_count": _avg(
                stroke_counts
            ),

            "pace_cv_percent": _cv(paces),

            "hr_cv_percent": _cv(hrs),
        },

        "segments": segments,

        "confidence": "HIGH",
    }


# ============================================================
# Prescribed swim workout matching
# ============================================================

def _duration_close(actual, expected, tolerance):
    if actual is None or expected is None:
        return False

    return abs(actual - expected) <= tolerance


def _distance_close(actual, expected, tolerance=2):
    if actual is None or expected is None:
        return False

    return abs(actual - expected) <= tolerance


def analyze_structured_swim(
    laps,
    work_distance_m=None,
    reps=None,
    stroke=None,
    recovery_seconds=None,
    recovery_tolerance_seconds=8,
):
    """
    Match a prescribed swim workout against Garmin-native laps.

    Example:

        analyze_structured_swim(
            laps,
            work_distance_m=100,
            reps=5,
            stroke="freestyle",
            recovery_seconds=15,
        )
    """

    if not laps:
        return {
            "error": "No Garmin swim laps found.",
            "confidence": "LOW",
        }

    swim_laps = []

    for index, lap in enumerate(laps, start=1):

        if _is_rest_lap(lap):
            continue

        distance = _lap_distance(lap)

        if distance is None:
            continue

        if work_distance_m is not None:
            if not _distance_close(
                distance,
                work_distance_m,
            ):
                continue

        if stroke:
            lap_stroke = _lap_stroke(lap)

            if lap_stroke:
                if lap_stroke.lower() != stroke.lower():
                    continue

        swim_laps.append(
            (
                index,
                lap,
            )
        )

    if reps is not None:
        swim_laps = swim_laps[:reps]

    analyzed_reps = []

    for index, lap in swim_laps:

        metrics = _swim_metrics(lap)

        rep = {
            "rep": len(analyzed_reps) + 1,
            "lap_index": index,
            "metrics": metrics,
        }

        # Find Garmin rest immediately following this lap.
        lap_position = index - 1

        if lap_position + 1 < len(laps):

            following = laps[
                lap_position + 1
            ]

            if _is_rest_lap(following):

                rest_duration = _lap_duration(
                    following
                )

                rep["recovery"] = {
                    "lap_index": index + 1,
                    "duration_seconds": _round(
                        rest_duration
                    ),
                    "duration": _format_time(
                        rest_duration
                    ),
                }

                if recovery_seconds is not None:
                    rep["recovery"][
                        "target_seconds"
                    ] = recovery_seconds

                    rep["recovery"][
                        "within_target"
                    ] = _duration_close(
                        rest_duration,
                        recovery_seconds,
                        recovery_tolerance_seconds,
                    )

        analyzed_reps.append(rep)

    # --------------------------------------------------------
    # Rep consistency
    # --------------------------------------------------------

    paces = [
        r["metrics"].get(
            "pace_seconds_per_100m"
        )
        for r in analyzed_reps
    ]

    hrs = [
        r["metrics"].get("avg_hr")
        for r in analyzed_reps
    ]

    stroke_rates = [
        r["metrics"].get(
            "avg_stroke_rate"
        )
        for r in analyzed_reps
    ]

    swolfs = [
        r["metrics"].get("avg_swolf")
        for r in analyzed_reps
    ]

    return {
        "sport": "swim",

        "prescription": {
            "work_distance_m": work_distance_m,
            "reps": reps,
            "stroke": stroke,
            "recovery_seconds": recovery_seconds,
        },

        "reps_found": len(analyzed_reps),

        "reps": analyzed_reps,

        "summary": {
            "target_reps": reps,
            "completed_reps": len(
                analyzed_reps
            ),

            "completion_percent": (
                round(
                    len(analyzed_reps)
                    / reps
                    * 100,
                    1,
                )
                if reps
                else None
            ),

            "avg_pace_seconds_per_100m": _avg(
                paces
            ),

            "pace_cv_percent": _cv(
                paces
            ),

            "avg_hr": _avg(
                hrs
            ),

            "avg_stroke_rate": _avg(
                stroke_rates
            ),

            "avg_swolf": _avg(
                swolfs
            ),

            "first_rep_pace": _first(
                paces
            ),

            "last_rep_pace": _last(
                paces
            ),

            "pace_change_percent": (
                _percent_change(
                    _first(paces),
                    _last(paces),
                )
            ),
        },

        "confidence": (
            "HIGH"
            if analyzed_reps
            else "LOW"
        ),
    }


# ============================================================
# Structured bike/run interval matching
# ============================================================

def _find_structured_block(
    laps,
    work_seconds,
    recovery_seconds,
    reps_per_set,
    sets,
    between_set_recovery_seconds=None,
    tolerance_seconds=8,
):
    """
    Match prescribed work/recovery intervals against Garmin laps.

    Garmin lap boundaries are treated as authoritative.
    """

    matches = []

    i = 0

    total_reps_target = reps_per_set * sets

    while (
        i < len(laps)
        and len(matches) < total_reps_target
    ):

        work_lap = laps[i]

        work_duration = _lap_duration(
            work_lap
        )

        if not _duration_close(
            work_duration,
            work_seconds,
            tolerance_seconds,
        ):
            i += 1
            continue

        recovery_lap = None

        if i + 1 < len(laps):

            candidate = laps[i + 1]

            candidate_duration = _lap_duration(
                candidate
            )

            if _duration_close(
                candidate_duration,
                recovery_seconds,
                tolerance_seconds,
            ):
                recovery_lap = candidate

        matches.append({
            "work_lap_index": i + 1,
            "work_lap": work_lap,
            "recovery_lap_index": (
                i + 2
                if recovery_lap
                else None
            ),
            "recovery_lap": recovery_lap,
        })

        i += 2 if recovery_lap else 1

    return matches


def _build_interval(
    lap,
    lap_index,
    sport,
):
    return {
        "lap_index": lap_index,
        "metrics": _metrics_for_sport(
            lap,
            sport,
        ),
    }


def _build_recovery(
    lap,
    lap_index,
):
    duration = _lap_duration(lap)

    return {
        "lap_index": lap_index,
        "duration_seconds": _round(
            duration
        ),
        "duration": _format_time(
            duration
        ),
    }


def analyze_garmin_laps(
    laps,
    samples=None,
    work_seconds=40,
    recovery_seconds=20,
    reps_per_set=6,
    sets=1,
    between_set_recovery_seconds=None,
    sport="bike",
):
    """
    Analyze a prescribed workout using Garmin-native laps.

    Bike/run:
        Uses prescribed time-based lap structure.

    Swim:
        Uses Garmin-native swim lap structure.
        Swim should generally use analyze_structured_swim()
        when a distance-based prescription is known.
    """

    if not laps:
        return {
            "error": "No Garmin lap data found.",
            "confidence": "LOW",
        }

    sport = sport.lower()

    # --------------------------------------------------------
    # Swim gets its own analysis path.
    # --------------------------------------------------------

    if sport == "swim":
        return _analyze_swim_laps(laps)

    # --------------------------------------------------------
    # Bike / Run structured intervals
    # --------------------------------------------------------

    matches = _find_structured_block(
        laps=laps,
        work_seconds=work_seconds,
        recovery_seconds=recovery_seconds,
        reps_per_set=reps_per_set,
        sets=sets,
        between_set_recovery_seconds=(
            between_set_recovery_seconds
        ),
    )

    if not matches:
        return {
            "sport": sport,
            "error": (
                "No prescribed interval structure "
                "matched Garmin lap durations."
            ),
            "prescription": {
                "work_seconds": work_seconds,
                "recovery_seconds": recovery_seconds,
                "reps_per_set": reps_per_set,
                "sets": sets,
            },
            "confidence": "LOW",
        }

    # --------------------------------------------------------
    # Build reps
    # --------------------------------------------------------

    reps = []

    for n, match in enumerate(
        matches,
        start=1,
    ):

        work = _build_interval(
            match["work_lap"],
            match["work_lap_index"],
            sport,
        )

        recovery = None

        if match["recovery_lap"]:

            recovery = _build_recovery(
                match["recovery_lap"],
                match["recovery_lap_index"],
            )

        reps.append({
            "rep": n,
            "work": work,
            "recovery": recovery,
        })

    # --------------------------------------------------------
    # Separate sets
    # --------------------------------------------------------

    analyzed_sets = []

    for set_number in range(sets):

        start = (
            set_number
            * reps_per_set
        )

        end = start + reps_per_set

        set_reps = reps[start:end]

        if not set_reps:
            break

        analyzed_sets.append({
            "set": set_number + 1,
            "reps": set_reps,
        })

    # --------------------------------------------------------
    # Objective summary
    # --------------------------------------------------------

    metric_key = (
        "avg_power"
        if sport == "bike"
        else "avg_speed"
    )

    primary_values = []

    hr_values = []

    for rep in reps:

        metrics = rep["work"]["metrics"]

        value = metrics.get(metric_key)

        if value is not None:
            primary_values.append(value)

        hr = metrics.get("avg_hr")

        if hr is not None:
            hr_values.append(hr)

    summary = {
        "completed_reps": len(reps),

        "target_reps": (
            reps_per_set * sets
        ),

        "completion_percent": round(
            len(reps)
            / (reps_per_set * sets)
            * 100,
            1,
        ),

        "avg_primary_metric": _avg(
            primary_values
        ),

        "first_primary_metric": _first(
            primary_values
        ),

        "last_primary_metric": _last(
            primary_values
        ),

        "primary_metric_change_percent": (
            _percent_change(
                _first(primary_values),
                _last(primary_values),
            )
        ),

        "primary_metric_cv_percent": _cv(
            primary_values
        ),

        "avg_hr": _avg(
            hr_values
        ),

        "hr_change": _change(
            _first(hr_values),
            _last(hr_values),
        ),

        "hr_change_percent": (
            _percent_change(
                _first(hr_values),
                _last(hr_values),
            )
        ),
    }

    return {
        "sport": sport,

        "prescription": {
            "work_seconds": work_seconds,
            "recovery_seconds": recovery_seconds,
            "reps_per_set": reps_per_set,
            "sets": sets,
            "between_set_recovery_seconds": (
                between_set_recovery_seconds
            ),
        },

        "sets": analyzed_sets,

        "summary": summary,

        "matched_lap_indices": [
            {
                "work": r["work"]["lap_index"],
                "recovery": (
                    r["recovery"]["lap_index"]
                    if r["recovery"]
                    else None
                ),
            }
            for r in reps
        ],

        "confidence": "HIGH",
    }


# ============================================================
# Backward compatibility
# ============================================================

def analyze_structured_intervals(
    samples=None,
    **kwargs,
):
    """
    Deprecated compatibility wrapper.

    The old implementation attempted to infer intervals from
    arbitrary 5-second samples. That approach produced false
    interval boundaries.

    Use analyze_garmin_laps() instead.
    """

    return {
        "error": (
            "analyze_structured_intervals() is deprecated. "
            "Use analyze_garmin_laps() with Garmin-native laps."
        ),
        "confidence": "LOW",
    }