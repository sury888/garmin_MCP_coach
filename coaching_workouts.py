"""Native Garmin workout analysis for the coaching context.

This module deliberately uses Garmin-native lap boundaries only. It never
infers work/recovery intervals from arbitrary sample timing.
"""
from statistics import mean, pstdev

from database import get_session, Activity
from garmin_client import GarminClient
from intervals_analysis import _metrics_for_sport, _is_rest_lap

ENDURANCE_TYPES = {
    "bike": {"cycling", "indoor_cycling", "virtual_ride", "road_biking", "mountain_biking"},
    "run": {"running", "treadmill_running", "trail_running"},
    "swim": {"lap_swimming", "swimming", "open_water_swimming"},
}


def _sport_for_activity(activity_type):
    value = (activity_type or "").lower()
    for sport, types in ENDURANCE_TYPES.items():
        if value in types or any(t in value for t in types):
            return sport
    return None


def _pct_change(first, last):
    if first in (None, 0) or last is None:
        return None
    return round((last - first) / abs(first) * 100, 2)


def _cv(values):
    values = [float(v) for v in values if v is not None]
    if len(values) < 2 or mean(values) == 0:
        return None
    return round(pstdev(values) / abs(mean(values)) * 100, 2)


def _quality_flags(sport, metrics):
    flags = []
    if sport == "bike":
        avg_power = metrics.get("avg_power")
        np = metrics.get("normalized_power")
        if avg_power is not None and np is not None and np + 1e-9 < avg_power:
            flags.append("normalized_power_below_average_power")
    for key in ("avg_hr", "avg_power", "avg_speed", "avg_cadence"):
        value = metrics.get(key)
        if value is not None and value < 0:
            flags.append(f"invalid_negative_{key}")
    return flags


def _native_lap_analysis(laps, sport):
    records = []
    excluded = []

    for idx, lap in enumerate(laps or [], start=1):
        if not isinstance(lap, dict):
            excluded.append({"lap": idx, "reason": "non_dict_lap"})
            continue

        if sport == "swim" and _is_rest_lap(lap):
            excluded.append({"lap": idx, "reason": "rest_lap"})
            continue

        metrics = _metrics_for_sport(lap, sport)
        distance = metrics.get("distance_m")
        duration = metrics.get("duration_seconds")

        if sport == "swim":
            pace = metrics.get("pace_seconds_per_100m")
            invalid = distance is not None and distance > 0 and (pace is None or pace < 20 or pace > 300)
            if invalid:
                excluded.append({"lap": idx, "reason": "invalid_swim_pace", "metrics": metrics})
                continue

        metrics["lap_index"] = idx
        metrics["intensity_type"] = lap.get("intensityType")
        if sport == "run":
            metrics["running_mechanics"] = {
                "cadence_spm": metrics.get("avg_cadence"),
                "ground_contact_time_ms": metrics.get("ground_contact_time"),
                "vertical_oscillation_cm": metrics.get("vertical_oscillation"),
                "vertical_ratio_percent": metrics.get("vertical_ratio"),
                "stride_length_cm": metrics.get("stride_length"),
            }
        metrics["start_time"] = lap.get("startTimeGMT") or lap.get("startTimeLocal")
        metrics["data_quality_flags"] = _quality_flags(sport, metrics)
        records.append(metrics)

    primary_key = {
        "bike": "avg_power",
        "run": "avg_speed",
        "swim": "pace_seconds_per_100m",
    }[sport]

    primary = [r.get(primary_key) for r in records if r.get(primary_key) is not None]
    hr = [r.get("avg_hr") for r in records if r.get("avg_hr") is not None]

    summary = {
        "recorded_laps": len(records),
        "excluded_laps": len(excluded),
        "primary_metric": primary_key,
        "primary_mean": round(mean(primary), 4) if primary else None,
        "primary_cv_percent": _cv(primary),
        "first_primary": primary[0] if primary else None,
        "last_primary": primary[-1] if primary else None,
        "primary_change_percent": _pct_change(primary[0], primary[-1]) if primary else None,
        "first_hr": hr[0] if hr else None,
        "last_hr": hr[-1] if hr else None,
        "hr_change": round(hr[-1] - hr[0], 2) if len(hr) >= 2 else None,
    }

    # Run-specific repeated-effort stability: compare laps in the same
    # duration neighborhood rather than pretending every lap is equivalent.
    if sport == "run":
        long_laps = [
            r for r in records
            if r.get("duration_seconds") is not None
            and 240 <= r["duration_seconds"] <= 330
            and r.get("avg_power") is not None
        ]
        if len(long_laps) >= 2:
            powers = [r["avg_power"] for r in long_laps]
            speeds = [r["avg_speed"] for r in long_laps if r.get("avg_speed") is not None]
            hrs = [r["avg_hr"] for r in long_laps if r.get("avg_hr") is not None]
            summary["repeated_long_efforts"] = {
                "laps": [r["lap_index"] for r in long_laps],
                "power_mean": round(mean(powers), 2),
                "power_cv_percent": _cv(powers),
                "speed_mean": round(mean(speeds), 4) if speeds else None,
                "speed_cv_percent": _cv(speeds),
                "hr_values": hrs,
                "mechanics": [
                    {
                        "lap": r["lap_index"],
                        "cadence": r.get("avg_cadence"),
                        "gct_ms": r.get("ground_contact_time"),
                        "vertical_oscillation": r.get("vertical_oscillation"),
                        "vertical_ratio": r.get("vertical_ratio"),
                        "stride_length": r.get("stride_length"),
                    }
                    for r in long_laps
                ],
            }

    return {
        "sport": sport,
        "laps": records,
        "excluded_laps": excluded,
        "summary": summary,
        "boundary_source": "GARMIN_NATIVE_LAPS",
        "interval_boundaries_inferred": False,
    }


def build_today_workout_analysis():
    """Fetch and analyze today's endurance sessions using native Garmin laps."""
    session = get_session()
    activities = (
        session.query(Activity)
        .order_by(Activity.activity_date.asc(), Activity.activity_id.asc())
        .all()
    )
    session.close()

    from datetime import date
    today = date.today()
    todays = [a for a in activities if a.activity_date == today]
    todays = [a for a in todays if _sport_for_activity(a.activity_type)]

    if not todays:
        return {"date": str(today), "sessions": [], "errors": []}

    garmin = GarminClient()
    garmin.login()
    sessions = []
    errors = []

    for activity in todays:
        sport = _sport_for_activity(activity.activity_type)
        try:
            splits = garmin.get_activity_splits(activity.activity_id) or {}
            laps = splits.get("lapDTOs", [])
            analysis = _native_lap_analysis(laps, sport)
            sessions.append({
                "activity_id": activity.activity_id,
                "name": activity.activity_name,
                "activity_type": activity.activity_type,
                "sport": sport,
                "date": str(activity.activity_date),
                "session_summary": {
                    "duration_seconds": activity.duration_seconds,
                    "distance_meters": activity.distance_meters,
                    "avg_heart_rate": activity.avg_heart_rate,
                    "max_heart_rate": activity.max_heart_rate,
                    "avg_power": activity.avg_power,
                    "normalized_power": activity.normalized_power,
                    "avg_cadence": activity.avg_cadence,
                    "training_load": activity.training_load,
                },
                "lap_analysis": analysis,
            })
        except Exception as exc:
            errors.append({
                "activity_id": activity.activity_id,
                "sport": sport,
                "error": str(exc),
            })

    historical = {}
    try:
        from performance_engine import get_peak_records, get_historical_records
        for sport in ("bike", "run", "swim"):
            historical[sport] = {
                "all_time_peak_records": get_peak_records(sport, None),
                "recent_records": get_historical_records(sport, 365, 20),
            }
    except Exception as exc:
        historical = {"error": f"Historical performance context unavailable: {exc}"}

    return {
        "date": str(today),
        "sessions": sessions,
        "historical_performance": historical,
        "errors": errors,
        "data_policy": {
            "native_laps_only": True,
            "interval_boundaries_inferred": False,
            "training_readiness_used": False,
            "session_averages_are_supporting_context": True,
        },
    }
