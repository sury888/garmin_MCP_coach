from datetime import date, timedelta

from database import get_session, DailyHealth, Activity
from freshness import is_data_fresh
from sync import sync_latest_garmin_data

def get_health_history(days=30):
    session = get_session()

    start_date = date.today() - timedelta(days=days - 1)

    records = (
        session.query(DailyHealth)
        .filter(DailyHealth.date >= start_date)
        .order_by(DailyHealth.date.asc())
        .all()
    )

    session.close()

    return records


def get_activity_history(days=30):
    session = get_session()

    start_date = date.today() - timedelta(days=days - 1)

    records = (
        session.query(Activity)
        .filter(Activity.activity_date >= start_date)
        .order_by(Activity.activity_date.asc())
        .all()
    )

    session.close()

    return records


def calculate_training_summary(days=7):

    activities = get_activity_history(days)

    total_duration = 0
    total_distance = 0
    total_load = 0

    sport_summary = {}

    for activity in activities:

        duration = activity.duration_seconds or 0
        distance = activity.distance_meters or 0
        load = activity.training_load or 0

        total_duration += duration
        total_distance += distance
        total_load += load

        sport = activity.activity_type or "unknown"

        if sport not in sport_summary:
            sport_summary[sport] = {
                "activities": 0,
                "duration": 0,
                "distance": 0,
                "training_load": 0,
            }

        sport_summary[sport]["activities"] += 1
        sport_summary[sport]["duration"] += duration
        sport_summary[sport]["distance"] += distance
        sport_summary[sport]["training_load"] += load

    return {
        "days": days,
        "activities": len(activities),
        "total_duration_seconds": total_duration,
        "total_distance_meters": total_distance,
        "total_training_load": total_load,
        "sport_summary": sport_summary,
    }

def generate_coaching_context(days=7, baseline_days=30, include_today_workouts=False):
    """
    Generate a complete coaching snapshot from the athlete's Garmin data.

    Automatically refreshes Garmin data when the existing data is stale.
    """

    sync_error = None
    if not is_data_fresh():
        try:
            sync_latest_garmin_data()
        except Exception as exc:
            # Coaching context should remain usable from the latest locally
            # cached Garmin data if a live sync intermittently times out.
            sync_error = f"Live Garmin refresh failed: {type(exc).__name__}: {exc}"

    from baseline import calculate_baselines
    from health_trends import get_health_trends
    from coach import calculate_recovery_score
    from training_summary import get_training_summary
    from workout_relationships import analyze_workout_recovery
    from coaching_workouts import build_today_workout_analysis

    health_history = get_health_history(baseline_days)
    activity_history = get_activity_history(days)

    ...

    if not health_history:
        return {"error": "No health data available"}

    latest = health_history[-1]

    # Personal baseline
    baselines = calculate_baselines(baseline_days)

    # Long-term health trends
    trends = get_health_trends(baseline_days)

    # Recovery score
    recovery = calculate_recovery_score()

    # Recent training
    training = get_training_summary(days)

    # Workout → recovery relationship
    workout_recovery = analyze_workout_recovery(days)
    if include_today_workouts:
        try:
            today_workouts = build_today_workout_analysis()
        except Exception as exc:
            today_workouts = {
                "date": str(latest.date),
                "sessions": [],
                "errors": [
                    {"error": f"Live workout-lap analysis unavailable: {type(exc).__name__}: {exc}"}
                ],
                "data_policy": {
                    "native_laps_only": True,
                    "interval_boundaries_inferred": False,
                    "training_readiness_used": False,
                },
            }
    else:
        today_workouts = {
            "not_loaded": True,
            "tool": "get_today_workout_intervals",
            "reason": "Kept separate to avoid coupling a live Garmin lap fetch to the main coaching-context call.",
        }

    # Coaching flags
    flags = []

    if trends.get("overall_recovery_trend") == "declining_recovery":
        flags.append("Overall recovery trend is declining.")

    # HRV
    hrv_baseline = baselines.get("hrv", {}).get("mean")

    if hrv_baseline and latest.hrv is not None:
        if latest.hrv < hrv_baseline * 0.85:
            flags.append(
                "HRV is significantly below personal baseline."
            )

    # Resting HR
    rhr_baseline = baselines.get("resting_hr", {}).get("mean")

    if rhr_baseline and latest.resting_hr is not None:
        if latest.resting_hr > rhr_baseline * 1.10:
            flags.append(
                "Resting HR is significantly elevated."
            )

    # ACWR
    if latest.acwr is not None and latest.acwr >= 1.2:
        flags.append(
            f"ACWR is elevated at {latest.acwr:.2f}."
        )

    return {
        "date": str(latest.date),

        "data_refresh": {
            "fresh_at_start": sync_error is None,
            "sync_error": sync_error,
        },

        "recovery": recovery,

        "current_health": {
            "resting_hr": latest.resting_hr,
            "hrv": latest.hrv,
            "sleep_hours": latest.sleep_hours,
            "sleep_score": latest.sleep_score,
            "body_battery": latest.body_battery,
            "stress": latest.stress,
            "acute_load": latest.acute_load,
            "chronic_load": latest.chronic_load,
            "acwr": latest.acwr,
            "training_status": latest.training_status,
            "training_status_feedback": latest.training_status_feedback,
        },

        "health_trends": trends,

        "recent_training": training,

        "workout_recovery": workout_recovery,

        "today_workouts": today_workouts,

        "coaching_priority": [
            "workout_execution",
            "interval_or_lap_response",
            "historical_comparison",
            "training_load",
            "recovery_context",
        ],

        "key_flags": flags,
    }

