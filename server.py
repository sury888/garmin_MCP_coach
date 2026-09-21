from datetime import date, datetime

from mcp.server import MCPServer

from analytics import (
    get_health_history,
    get_activity_history,
    generate_coaching_context,
)
from daily_report import generate_daily_report
from training_summary import get_training_summary
from health_trends import get_health_trends
from coach import (
    calculate_recovery_score,
    generate_adjusted_workout,
    analyze_workout_response,
)
from recommendations import get_workout_recommendation
from workout_recommendation import evaluate_planned_workout
from database import save_planned_workout, get_planned_workout
from activity_details import parse_activity_details
from interval_recovery import analyze_interval_recovery
from garmin_client import GarminClient
from intervals_analysis import (
    analyze_garmin_laps,
    analyze_structured_swim,
)
from sync import sync_latest_garmin_data, sync_activity_history as sync_activity_history_data
from training_load import build_training_load, get_training_load, get_current_training_load
from database import AthleteProfile, get_session
from weather_context import fetch_activity_weather, get_activity_weather
from coaching_workouts import build_today_workout_analysis
from coaching_tables import save_annotation, get_annotation, save_treadmill_intervals, get_treadmill_intervals
from performance_engine import (
    build_performance_database, get_peak_records, get_historical_records,
    process_activity_performance, get_hr_controlled_records,
    get_highest_hr_history, get_leaderboard, get_durability_records,
)

mcp = MCPServer("Garmin Coach")


# ============================================================
# PERFORMANCE ENGINE
# ============================================================

@mcp.tool()
def get_activity_weather_tool(activity_id: int) -> dict:
    """Return historical weather matched to a Garmin activity timestamp/location."""
    return get_activity_weather(activity_id)


@mcp.tool()
def build_performance_engine(
    days: int | None = 90,
    max_activities: int | None = None,
    weight_kg: float | None = None,
    batch_size: int = 10,
    resume: bool = True,
) -> dict:
    """Build performance records in small resumable batches."""
    return build_performance_database(
        days=days,
        max_activities=max_activities,
        weight_kg=weight_kg,
        batch_size=batch_size,
        resume=resume,
    )

@mcp.tool()
def sync_activity_history(days: int = 3650, chunk_days: int = 30) -> dict:
    """Sync Garmin activities over a long history using date-range chunks."""
    return sync_activity_history_data(days=days, chunk_days=chunk_days)


@mcp.tool()
def get_peak_performance(sport: str, window_days: int | None = None) -> dict:
    """Return the best performance at every duration/distance."""
    sport=sport.lower()
    if sport not in {"bike","run","swim"}: return {"error":"sport must be bike, run, or swim"}
    return {"sport":sport,"window_days":window_days,"records":get_peak_records(sport,window_days)}

@mcp.tool()
def get_performance_history(sport: str, window_days: int | None = 365, limit: int = 100) -> dict:
    """Return historical performance records for a sport."""
    sport=sport.lower()
    if sport not in {"bike","run","swim"}: return {"error":"sport must be bike, run, or swim"}
    return {"sport":sport,"window_days":window_days,"records":get_historical_records(sport,window_days,limit)}

@mcp.tool()
def analyze_activity_performance(activity_id: int, weight_kg: float | None = None) -> dict:
    """Analyze and cache one activity's performance curves."""
    return process_activity_performance(activity_id,weight_kg)

@mcp.tool()
def get_hr_controlled_performance(sport: str, hr_limit: int = 165, window_days: int | None = None) -> dict:
    """Best bike power or run pace at or below an average-HR ceiling."""
    sport=sport.lower()
    return {"sport":sport,"hr_limit":hr_limit,"window_days":window_days,"records":get_hr_controlled_records(sport,hr_limit,window_days)}

@mcp.tool()
def get_highest_hr_history(sport: str, window_days: int | None = None) -> dict:
    """Highest observed average HR for each performance duration."""
    sport=sport.lower()
    if sport not in {"bike","run"}: return {"error":"sport must be bike or run"}
    return {"sport":sport,"window_days":window_days,"records":get_highest_hr_history(sport,window_days)}

@mcp.tool()
def get_performance_leaderboard(sport: str, metric: str = "peak", window_days: int | None = None, limit: int = 20) -> dict:
    """Rank stored performance records for a sport."""
    sport=sport.lower()
    if sport not in {"bike","run","swim"}: return {"error":"sport must be bike, run, or swim"}
    return {"sport":sport,"metric":metric,"window_days":window_days,"records":get_leaderboard(sport,metric,window_days,limit)}

@mcp.tool()
def get_durability_performance(sport: str | None = None, window_days: int | None = None) -> dict:
    """Return long-session and brick durability records."""
    return {"sport":sport,"window_days":window_days,"records":get_durability_records(sport,window_days)}


# ============================================================
# CURRENT HEALTH
# ============================================================

@mcp.tool()
def sync_garmin_now() -> dict:
    """Force a fresh sync of the latest Garmin activities and health data."""
    return sync_latest_garmin_data()

@mcp.tool()
def get_activity_full_report(
    activity_id: int,
) -> dict:
    """
    Return all Garmin lap/split data available for an activity.
    """

    garmin = GarminClient()
    garmin.login()

    details = garmin.get_activity_details(
        activity_id
    )

    splits = garmin.get_activity_splits(
        activity_id
    )

    samples = parse_activity_details(
        details
    )

    return {
        "activity_id": activity_id,

        "sample_count": len(samples),

        "laps": splits.get(
            "lapDTOs",
            []
        ),

        "lengths": [
            length
            for lap in splits.get(
                "lapDTOs",
                []
            )
            for length in lap.get(
                "lengthDTOs",
                []
            )
        ],

        "samples": samples,
    }

@mcp.tool()
def analyze_structured_activity(
    activity_id: int,
    work_seconds: int,
    recovery_seconds: int,
    reps_per_set: int,
    sets: int = 1,
    between_set_recovery_seconds: int | None = None,
    sport: str = "bike",
) -> dict:
    """
    Analyze a prescribed bike or run interval workout
    using Garmin-native laps.
    """

    garmin = GarminClient()
    garmin.login()

    splits = garmin.get_activity_splits(
        activity_id
    )

    laps = splits.get(
        "lapDTOs",
        []
    )

    if not laps:
        return {
            "error": "No Garmin lap data found.",
            "activity_id": activity_id,
        }

    # Swim is distance/lap based, not time-interval based.
    if sport.lower() == "swim":
        return make_json_safe(
            analyze_garmin_laps(
                laps=laps,
                sport="swim",
            )
        )

    details = garmin.get_activity_details(
        activity_id
    )

    samples = parse_activity_details(
        details
    )

    analysis = analyze_garmin_laps(
        laps=laps,
        samples=samples,
        work_seconds=work_seconds,
        recovery_seconds=recovery_seconds,
        reps_per_set=reps_per_set,
        sets=sets,
        between_set_recovery_seconds=(
            between_set_recovery_seconds
        ),
        sport=sport,
    )

    return make_json_safe({
        "activity_id": activity_id,
        "analysis": analysis,
    })

@mcp.tool()
def analyze_swim_activity(
    activity_id: int,
) -> dict:
    """Analyze Garmin-native swim laps."""

    garmin = GarminClient()
    garmin.login()

    splits = garmin.get_activity_splits(
        activity_id
    )

    laps = splits.get(
        "lapDTOs",
        []
    )

    if not laps:
        return {
            "error": "No Garmin swim laps found.",
            "activity_id": activity_id,
        }

    analysis = analyze_structured_swim(
        laps=laps
    )

    return make_json_safe({
        "activity_id": activity_id,
        "analysis": analysis,
    })
    
@mcp.tool()
def save_activity_coaching_annotation(
    activity_id: int,
    note: str | None = None,
    bike_position: str | None = None,
    interval_positions: dict | None = None,
    swim_subtype: str | None = None,
    swim_set_description: str | None = None,
    swim_lap_indices: list[int] | None = None,
) -> dict:
    """Save user-confirmed context for an activity or swim section.

    swim_subtype may be kick, pull, paddles, drill, choice, or another
    user-defined label. Garmin may call these laps Drill; this annotation
    preserves the athlete's more precise classification for future comparisons.
    """
    return make_json_safe(save_annotation(
        activity_id=activity_id, note=note, bike_position=bike_position,
        interval_positions=interval_positions, swim_subtype=swim_subtype,
        swim_set_description=swim_set_description, swim_lap_indices=swim_lap_indices,
    ))


@mcp.tool()
def save_manual_treadmill_intervals(
    activity_id: int,
    intervals: list[dict],
) -> dict:
    """Save athlete-reported treadmill interval data.

    Pace/distance from Garmin treadmill recordings are not used as objective
    pace data. The athlete can supply the actual target pace and interval
    timing while Garmin-derived HR, cadence, running power, and dynamics can
    be stored alongside each interval.
    """
    return make_json_safe(save_treadmill_intervals(activity_id, intervals))


@mcp.tool()
def get_manual_treadmill_intervals(activity_id: int) -> dict:
    """Retrieve manually reported treadmill intervals for an activity."""
    return make_json_safe(get_treadmill_intervals(activity_id))

@mcp.tool()
def analyze_interval_recovery_tool(
    activity_id: int,
    sport: str,
    work_lap_indices: list[int],
    recovery_lap_indices: list[int],
    manual_work_target_paces: list[str] | None = None,
) -> dict:
    """Analyze bike/run interval recoveries using detailed Garmin samples.

    Lap indices are 1-based. True minimum HR is calculated from detailed HR
    samples when timestamps map to the selected recovery laps. For treadmill
    runs, manual pace remains authoritative.
    """
    return make_json_safe(
        analyze_interval_recovery(
            activity_id, sport, work_lap_indices, recovery_lap_indices,
            manual_work_target_paces,
        )
    )


@mcp.tool()
def get_activity_coaching_annotation(activity_id: int) -> dict:
    """Retrieve saved user-confirmed activity or swim annotations."""
    return make_json_safe(get_annotation(activity_id) or {"activity_id": activity_id, "found": False})


@mcp.tool()
def get_today_workout_intervals() -> dict:
    """Return today's Garmin-native lap/interval analysis for endurance sessions.

    Uses only Garmin-recorded lap boundaries. Never infers interval boundaries.
    Training Readiness is intentionally excluded.
    """
    return make_json_safe(build_today_workout_analysis())


@mcp.tool()
def get_today_health() -> dict:
    """
    Get today's Garmin health, recovery, sleep,
    training readiness, and training-load metrics.

    Use this when you need the athlete's current
    physiological state.
    """

    health = get_health_history(30)

    if not health:
        return {
            "error": "No health data available."
        }

    today = health[-1]

    return {
        "date": str(today.date),

        "resting_hr": today.resting_hr,
        "hrv": today.hrv,
        "body_battery": today.body_battery,
        "stress": today.stress,

        "sleep_hours": today.sleep_hours,
        "sleep_score": today.sleep_score,

        "respiration_avg": today.respiration_avg,
        "respiration_min": today.respiration_min,
        "respiration_max": today.respiration_max,

        "training_readiness": today.training_readiness,
        "training_readiness_level": today.training_readiness_level,

        "acute_load": today.acute_load,
        "chronic_load": today.chronic_load,
        "acwr": today.acwr,

        "training_status": today.training_status,
        "training_status_feedback": today.training_status_feedback,
    }


# ============================================================
# RECENT ACTIVITIES
# ============================================================

@mcp.tool()
def get_recent_activities(days: int = 7) -> list:
    """
    Get Garmin activities from the last N days.

    Includes duration, distance, heart rate,
    power, running dynamics, training effect,
    training load, and other available metrics.
    """

    activities = get_activity_history(days)

    results = []

    for activity in activities:

        results.append({
            "id": activity.activity_id,
            "date": str(activity.activity_date),
            "name": activity.activity_name,
            "type": activity.activity_type,

            "duration_seconds": activity.duration_seconds,
            "distance_meters": activity.distance_meters,
            "calories": activity.calories,

            "avg_heart_rate": activity.avg_heart_rate,
            "max_heart_rate": activity.max_heart_rate,

            "avg_power": activity.avg_power,
            "max_power": activity.max_power,
            "normalized_power": activity.normalized_power,

            "avg_cadence": activity.avg_cadence,
            "avg_running_cadence": activity.avg_running_cadence,

            "avg_stride_length": activity.avg_stride_length,
            "ground_contact_time": activity.ground_contact_time,
            "vertical_oscillation": activity.vertical_oscillation,
            "vertical_ratio": activity.vertical_ratio,

            "elevation_gain": activity.elevation_gain,

            "training_effect": activity.training_effect,
            "training_load": activity.training_load,

            "avg_swolf": activity.avg_swolf,
            "total_strokes": activity.total_strokes,
            "pool_length": activity.pool_length,

            "vo2_max": activity.vo2max,
        })

    return results


# ============================================================
# DAILY COACHING REPORT
# ============================================================

@mcp.tool()
def get_daily_coaching_report() -> dict:
    """
    Generate a complete daily coaching report.

    Combines recovery, training load, personal baselines,
    health trends, and workout-to-recovery relationships.
    """

    report = generate_daily_report()

    if not report:
        return {
            "error": "Not enough data to generate report."
        }

    return report


# ============================================================
# TRAINING SUMMARY
# ============================================================

@mcp.tool()
def get_training_summary_tool(days: int = 7) -> dict:
    """
    Summarize training over the last N days.

    Includes activity count, duration, distance,
    training load, average daily load, and sport breakdown.
    """

    return get_training_summary(days)


# ============================================================
# HEALTH TRENDS
# ============================================================

@mcp.tool()
def get_health_trends_tool(days: int = 30) -> dict:
    """
    Analyze health and recovery trends over the last N days.

    Identifies changes in HRV, resting HR, sleep,
    Body Battery, readiness, training load, and ACWR.
    """

    return get_health_trends(days)


# ============================================================
# RECOVERY SCORE
# ============================================================

@mcp.tool()
def get_recovery_score() -> dict:
    """
    Calculate the athlete's current recovery score.

    Returns a 0-100 recovery score, status, and
    the physiological signals contributing to the score.

    Use this when evaluating whether the athlete
    is ready for training.
    """

    result = calculate_recovery_score()

    if not result:
        return {
            "error": "Not enough health data to calculate recovery."
        }

    return result


# ============================================================
# COMPLETE COACHING CONTEXT
# ============================================================

@mcp.tool()
def get_coaching_context(
    days: int = 7,
    baseline_days: int = 30,
    include_today_workouts: bool = False
) -> dict:
    """
    Get the complete athlete coaching context.

    This is the primary tool for answering coaching questions.

    Includes:

    - Current health
    - Recovery score
    - Personal baselines
    - Multi-day health trends
    - Recent training
    - Workout-to-recovery relationships
    - Key coaching flags
    - Optional today's native Garmin lap analysis (disabled by default so a
      live lap fetch cannot make the main context call time out)

    Use this tool before making a training recommendation.
    """

    context = generate_coaching_context(
        days=days,
        baseline_days=baseline_days,
        include_today_workouts=include_today_workouts
    )

    return make_json_safe(context)


# ============================================================
# TRAINING EVALUATION
# ============================================================

@mcp.tool()
def evaluate_training_today() -> dict:
    """
    Evaluate whether the athlete appears ready for
    normal, hard, or recovery-focused training today.

    This tool provides objective evidence from the
    athlete's current recovery and recent training.

    It does NOT prescribe a specific workout.
    The final coaching recommendation should consider
    the athlete's goals, training phase, and planned session.
    """

    context = generate_coaching_context(
        days=7,
        baseline_days=30
    )

    if not context:
        return {
            "error": "Unable to generate coaching context."
        }

    recovery = context.get("recovery", {})
    trends = context.get("health_trends", {})
    recent_training = context.get("recent_training", {})
    flags = context.get("key_flags", [])

    score = recovery.get("score")

    if score is None:
        readiness_category = "UNKNOWN"

    elif score >= 80:
        readiness_category = "READY_FOR_HARD_TRAINING"

    elif score >= 65:
        readiness_category = "READY_FOR_NORMAL_TRAINING"

    elif score >= 50:
        readiness_category = "CAUTION"

    else:
        readiness_category = "RECOVERY_FOCUSED"

    return {
        "date": context.get("date"),

        "recovery_score": score,

        "recovery_status": recovery.get("status"),

        "training_readiness_category": readiness_category,

        "health_trend":
            trends.get("overall_recovery_trend"),

        "recent_training": recent_training,

        "key_flags": flags,

        "decision_basis": {
            "recovery_score": score,
            "recovery_status": recovery.get("status"),
            "overall_recovery_trend":
                trends.get("overall_recovery_trend"),
            "key_flags": flags
        },

        "important_note":
            "This is an objective training assessment. "
            "Final workout selection should consider the planned "
            "session, race schedule, training phase, and athlete goals."
    }
@mcp.tool()
def get_workout_recommendation_tool(
    days: int = 7,
    baseline_days: int = 30
) -> dict:
    """
    Recommend an appropriate training intensity based on
    current recovery, health trends, recent training,
    and personal baselines.
    """

    return get_workout_recommendation(
        days=days,
        baseline_days=baseline_days
    )

@mcp.tool()
def evaluate_today_workout(
    sport: str,
    planned_duration_minutes: int,
    planned_intensity: str,
    planned_workout: str
) -> dict:
    """
    Evaluate today's planned workout against current recovery,
    health trends, recent training, and workout execution.
    """

    return evaluate_planned_workout(
        sport=sport,
        planned_duration_minutes=planned_duration_minutes,
        planned_intensity=planned_intensity,
        planned_workout=planned_workout
    )

@mcp.tool()
def set_todays_workout(
    sport: str,
    workout_name: str,
    duration_minutes: int,
    intensity: str,
    description: str = ""
) -> dict:
    """
    Save today's planned workout.
    """

    workout = save_planned_workout({
        "workout_date": date.today(),
        "sport": sport,
        "workout_name": workout_name,
        "duration_minutes": duration_minutes,
        "intensity": intensity,
        "description": description,
        "completed": 0
    })

    return {
        "success": True,
        "id": workout.id,
        "date": str(workout.workout_date),
        "sport": workout.sport,
        "workout_name": workout.workout_name,
        "duration_minutes": workout.duration_minutes,
        "intensity": workout.intensity,
        "description": workout.description
    }


@mcp.tool()
def get_todays_workout() -> dict:
    """
    Get today's planned workout.
    """

    workout = get_planned_workout(date.today())

    if not workout:
        return {
            "planned_workout": False,
            "message": "No workout planned for today."
        }

    return {
        "planned_workout": True,
        "id": workout.id,
        "date": str(workout.workout_date),
        "sport": workout.sport,
        "workout_name": workout.workout_name,
        "duration_minutes": workout.duration_minutes,
        "intensity": workout.intensity,
        "description": workout.description,
        "completed": bool(workout.completed)
    }

@mcp.tool()
def adjust_planned_workout(
    planned_workout: str,
    planned_duration_minutes: int,
    planned_intensity: str,
    sport: str
) -> dict:
    """
    Evaluate today's planned workout against the athlete's
    current recovery and return an adjusted prescription.
    """

    context = generate_coaching_context(
        days=7,
        baseline_days=30
    )

    return generate_adjusted_workout(
        planned_workout=planned_workout,
        planned_duration_minutes=planned_duration_minutes,
        planned_intensity=planned_intensity,
        sport=sport,
        coaching_context=context
    )
@mcp.tool()
def get_workout_response_analysis() -> dict:
    """
    Analyze how recent workouts have affected next-day recovery.
    """

    context = generate_coaching_context(
        days=7,
        baseline_days=30
    )

    return analyze_workout_response(context)

@mcp.tool()
def coach_today(
    planned_workout: str,
    planned_duration_minutes: int,
    planned_intensity: str,
    sport: str
) -> dict:
    """
    Full daily coaching decision.

    Combines recovery, health trends, recent training,
    workout-response history, and the planned workout
    to produce a coaching recommendation.
    """

    # Get complete athlete context
    context = generate_coaching_context(
        days=7,
        baseline_days=30
    )

    # Analyze workout-response history
    workout_response = analyze_workout_response(context)

    # Evaluate planned workout
    workout_decision = adjust_planned_workout(
        planned_workout=planned_workout,
        planned_duration_minutes=planned_duration_minutes,
        planned_intensity=planned_intensity,
        sport=sport
    )

    return {
        "date": context.get("date"),

        "athlete_status": {
            "recovery_score": context["recovery"]["score"],
            "recovery_status": context["recovery"]["status"],
            "health_trend": context["health_trends"][
                "overall_recovery_trend"
            ],
            "key_flags": context["key_flags"]
        },

        "recent_training": context["recent_training"],

        "workout_response": workout_response,

        "planned_workout": {
            "sport": sport,
            "workout": planned_workout,
            "duration_minutes": planned_duration_minutes,
            "intensity": planned_intensity
        },

        "decision": workout_decision,

        "coaching_summary": (
            "Decision generated from current recovery, "
            "multi-day health trends, recent training load, "
            "and observed workout-to-recovery response."
        )
    }

def make_json_safe(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()

    if isinstance(obj, dict):
        return {key: make_json_safe(value) for key, value in obj.items()}

    if isinstance(obj, list):
        return [make_json_safe(value) for value in obj]

    return obj



# ============================================================
# TRAINING LOAD ENGINE
# ============================================================

@mcp.tool()
def build_training_load_tool(days: int = 365) -> dict:
    """Build threshold-derived and Garmin-native training load history."""
    return build_training_load(days)


@mcp.tool()
def get_training_load_tool(days: int = 42) -> dict:
    """Return daily training load, ATL, CTL, and TSB history."""
    return {"days": days, "history": get_training_load(days)}


@mcp.tool()
def get_current_training_load_tool() -> dict:
    """Return current ATL/CTL/TSB and recent 7/28-day load."""
    return get_current_training_load()

@mcp.tool()
def set_training_thresholds(
    ftp_watts: float | None = None,
    run_threshold_pace_sec_per_km: float | None = None,
    css_sec_per_100m: float | None = None,
    weight_kg: float | None = None,
) -> dict:
    """Set athlete thresholds used for TSS-style load calculations.

    Run pace is seconds per km. Swim CSS is seconds per 100m. Only supplied
    values are changed.
    """
    session = get_session()
    try:
        profile = session.query(AthleteProfile).filter_by(id=1).first()
        if not profile:
            profile = AthleteProfile(id=1)
            session.add(profile)
        values = {
            "ftp": ftp_watts,
            "run_threshold_pace_sec_per_km": run_threshold_pace_sec_per_km,
            "css_sec_per_100m": css_sec_per_100m,
            "weight_kg": weight_kg,
        }
        for key, value in values.items():
            if value is not None:
                if float(value) <= 0:
                    raise ValueError(f"{key} must be greater than zero")
                setattr(profile, key, float(value))
        session.commit()
        return {
            "success": True,
            "ftp_watts": profile.ftp,
            "run_threshold_pace_sec_per_km": profile.run_threshold_pace_sec_per_km,
            "css_sec_per_100m": profile.css_sec_per_100m,
            "weight_kg": profile.weight_kg,
        }
    finally:
        session.close()


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":
    mcp.run()