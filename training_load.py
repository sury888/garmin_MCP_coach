"""High-performance training load calculations.

The engine keeps Garmin's native activity training load separate from
threshold-derived TSS-style metrics. TSS/IF are only calculated when the
athlete has supplied a valid threshold for that sport.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import isfinite

from sqlalchemy import text
from database import (
    Activity,
    AthleteProfile,
    DailyTrainingLoad,
    get_session,
)


def _num(value):
    try:
        value = float(value)
        return value if isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _is_treadmill(activity) -> bool:
    text = " ".join(str(getattr(activity, attr, "") or "") for attr in ("activity_type", "activity_name")).lower()
    return any(term in text for term in ("treadmill", "indoor run", "indoor_running", "virtual run"))


def _sport(activity_type: str | None) -> str:
    key = (activity_type or "").lower()
    if any(x in key for x in ("cycling", "bike", "biking")):
        return "bike"
    if any(x in key for x in ("running", "run", "trail_running")):
        return "run"
    if any(x in key for x in ("swim", "pool_swimming", "open_water")):
        return "swim"
    if any(x in key for x in ("strength", "weight_training")):
        return "strength"
    return "other"


def _get_profile():
    session = get_session()
    try:
        return session.query(AthleteProfile).filter_by(id=1).first()
    finally:
        session.close()


def _bike_load(activity, profile):
    duration = _num(activity.duration_seconds)
    np = _num(activity.normalized_power)
    avg_power = _num(activity.avg_power)
    ftp = _num(profile.ftp) if profile else None

    result = {"if": None, "tss": None, "normalized_power": np, "kJ": None, "vi": None}

    if duration:
        if avg_power is not None:
            result["kJ"] = avg_power * duration / 1000
        if np is not None and avg_power and avg_power > 0:
            result["vi"] = np / avg_power
        if np is not None and ftp and ftp > 0:
            intensity = np / ftp
            result["if"] = intensity
            result["tss"] = (duration / 3600) * (intensity ** 2) * 100

    return result


def _run_load(activity, profile):
    duration = _num(activity.duration_seconds)
    speed = _num(activity.avg_speed)
    threshold_pace = _num(profile.run_threshold_pace_sec_per_km) if profile else None

    treadmill = _is_treadmill(activity)
    result = {"if": None, "tss": None, "pace_sec_per_km": None,
              "treadmill": treadmill,
              "pace_source": "unreliable_treadmill" if treadmill else "garmin_speed"}

    # Garmin treadmill speed/pace is unreliable for this athlete.
    if treadmill:
        return result

    # Garmin activity speed is m/s. Convert to seconds/km.
    pace = 1000 / speed if speed and speed > 0 else None
    if pace is not None:
        result["pace_sec_per_km"] = pace
        if threshold_pace and threshold_pace > 0:
            intensity = threshold_pace / pace
            result["if"] = intensity
            result["tss"] = (duration / 3600) * (intensity ** 2) * 100 if duration else None

    return result


def _swim_load(activity, profile):
    duration = _num(activity.duration_seconds)
    distance = _num(activity.distance_meters)
    css = _num(profile.css_sec_per_100m) if profile else None

    result = {"if": None, "tss": None, "pace_sec_per_100m": None}
    if duration and distance and distance > 0:
        pace = duration / distance * 100
        result["pace_sec_per_100m"] = pace
        if css and css > 0:
            intensity = css / pace
            result["if"] = intensity
            result["tss"] = (duration / 3600) * (intensity ** 2) * 100
    return result


def calculate_activity_load(activity, profile=None):
    """Return objective load metrics for one activity.

    ``garmin_training_load`` is Garmin's native load and is never relabeled
    as TSS. ``tss`` is threshold-derived and is None when a valid threshold
    is unavailable.
    """
    sport = _sport(activity.activity_type)
    native = _num(activity.training_load)

    result = {
        "activity_id": activity.activity_id,
        "date": str(activity.activity_date),
        "sport": sport,
        "duration_seconds": _num(activity.duration_seconds) or 0,
        "garmin_training_load": native or 0,
        "tss": None,
        "if": None,
        "kJ": None,
        "vi": None,
        "pace_sec_per_km": None,
        "pace_sec_per_100m": None,
    }

    if sport == "bike":
        result.update(_bike_load(activity, profile))
    elif sport == "run":
        run = _run_load(activity, profile)
        result.update(run)
        result["pace_sec_per_km"] = run.get("pace_sec_per_km")
    elif sport == "swim":
        result.update(_swim_load(activity, profile))

    return result


def _ewma(values, days):
    """EWMA with a standard day-based decay (1/e weighting)."""
    if not values:
        return 0.0
    alpha = 2 / (days + 1)
    current = 0.0
    for value in values:
        current = alpha * value + (1 - alpha) * current
    return current


def _ensure_tss_balance_columns():
    """Lightweight SQLite migration for TSS ATL/CTL/TSB columns."""
    from database import engine
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(daily_training_load)"))}
        for name in ("tss_atl", "tss_ctl", "tss_tsb"):
            if name not in cols:
                conn.execute(text(f"ALTER TABLE daily_training_load ADD COLUMN {name} FLOAT"))


def build_training_load(days: int = 365):
    """Build daily training load history from stored Garmin activities."""
    days = max(1, int(days))
    _ensure_tss_balance_columns()
    today = date.today()
    start = today - timedelta(days=days - 1)

    profile = _get_profile()
    session = get_session()
    try:
        activities = (
            session.query(Activity)
            .filter(Activity.activity_date >= start, Activity.activity_date <= today)
            .order_by(Activity.activity_date.asc())
            .all()
        )

        daily = {}
        activity_metrics = []
        for activity in activities:
            metrics = calculate_activity_load(activity, profile)
            activity_metrics.append(metrics)
            bucket = daily.setdefault(str(activity.activity_date), {
                "date": activity.activity_date,
                "garmin_load": 0.0,
                "tss": 0.0,
                "tss_activities": 0,
                "duration_seconds": 0.0,
                "bike_tss": 0.0,
                "run_tss": 0.0,
                "swim_tss": 0.0,
                "strength_load": 0.0,
                "bike_duration": 0.0,
                "run_duration": 0.0,
                "swim_duration": 0.0,
            })
            bucket["garmin_load"] += metrics["garmin_training_load"]
            bucket["duration_seconds"] += metrics["duration_seconds"]
            if metrics["tss"] is not None:
                bucket["tss"] += metrics["tss"]
                bucket["tss_activities"] += 1
                if metrics["sport"] == "bike":
                    bucket["bike_tss"] += metrics["tss"]
                elif metrics["sport"] == "run":
                    bucket["run_tss"] += metrics["tss"]
                elif metrics["sport"] == "swim":
                    bucket["swim_tss"] += metrics["tss"]
            if metrics["sport"] == "strength":
                bucket["strength_load"] += metrics["garmin_training_load"]
            if metrics["sport"] == "bike":
                bucket["bike_duration"] += metrics["duration_seconds"]
            elif metrics["sport"] == "run":
                bucket["run_duration"] += metrics["duration_seconds"]
            elif metrics["sport"] == "swim":
                bucket["swim_duration"] += metrics["duration_seconds"]

        # Calculate EWMA from the full requested calendar window.
        ordered = []
        for i in range(days):
            d = start + timedelta(days=i)
            key = str(d)
            row = daily.get(key, {"date": d, "garmin_load": 0.0, "tss": 0.0,
                                  "tss_activities": 0, "duration_seconds": 0.0,
                                  "bike_tss": 0.0, "run_tss": 0.0, "swim_tss": 0.0,
                                  "strength_load": 0.0, "bike_duration": 0.0,
                                  "run_duration": 0.0, "swim_duration": 0.0})
            ordered.append(row)

        garmin_source = [r["garmin_load"] for r in ordered]
        tss_source = [r["tss"] if r["tss_activities"] else 0.0 for r in ordered]
        garmin_atl_series=[]; garmin_ctl_series=[]
        tss_atl_series=[]; tss_ctl_series=[]
        for i in range(len(ordered)):
            garmin_atl_series.append(_ewma(garmin_source[: i + 1], 7))
            garmin_ctl_series.append(_ewma(garmin_source[: i + 1], 42))
            tss_atl_series.append(_ewma(tss_source[: i + 1], 7))
            tss_ctl_series.append(_ewma(tss_source[: i + 1], 42))

        saved = 0
        for i, row in enumerate(ordered):
            existing = session.query(DailyTrainingLoad).filter_by(date=row["date"]).first()
            data = {
                "date": row["date"],
                "garmin_load": row["garmin_load"],
                "tss": row["tss"] if row["tss_activities"] else None,
                "tss_activities": row["tss_activities"],
                "duration_seconds": row["duration_seconds"],
                "bike_tss": row["bike_tss"] if row["bike_tss"] else None,
                "run_tss": row["run_tss"] if row["run_tss"] else None,
                "swim_tss": row["swim_tss"] if row["swim_tss"] else None,
                "strength_load": row["strength_load"],
                "atl": garmin_atl_series[i],
                "ctl": garmin_ctl_series[i],
                "tsb": garmin_ctl_series[i] - garmin_atl_series[i],
                "tss_atl": tss_atl_series[i],
                "tss_ctl": tss_ctl_series[i],
                "tss_tsb": tss_ctl_series[i] - tss_atl_series[i],
                "bike_duration_seconds": row["bike_duration"],
                "run_duration_seconds": row["run_duration"],
                "swim_duration_seconds": row["swim_duration"],
            }
            if existing:
                for k, v in data.items():
                    if k != "date":
                        setattr(existing, k, v)
            else:
                session.add(DailyTrainingLoad(**data))
            saved += 1

        session.commit()
        return {
            "success": True,
            "days": days,
            "activities": len(activities),
            "days_saved": saved,
            "thresholds": {
                "ftp_watts": getattr(profile, "ftp", None) if profile else None,
                "run_threshold_pace_sec_per_km": getattr(profile, "run_threshold_pace_sec_per_km", None) if profile else None,
                "css_sec_per_100m": getattr(profile, "css_sec_per_100m", None) if profile else None,
            },
            "tss_note": "TSS is calculated only for activities with a valid sport-specific threshold. Garmin native load remains separate.",
        }
    finally:
        session.close()


def get_training_load(days: int = 42):
    start = date.today() - timedelta(days=max(1, int(days)) - 1)
    session = get_session()
    try:
        rows = (
            session.query(DailyTrainingLoad)
            .filter(DailyTrainingLoad.date >= start)
            .order_by(DailyTrainingLoad.date.asc())
            .all()
        )
        return [
            {
                "date": str(r.date),
                "garmin_load": r.garmin_load,
                "tss": r.tss,
                "tss_activities": r.tss_activities,
                "bike_tss": r.bike_tss,
                "run_tss": r.run_tss,
                "swim_tss": r.swim_tss,
                "strength_load": r.strength_load,
                "duration_hours": (r.duration_seconds or 0) / 3600,
                "atl": r.atl,
                "ctl": r.ctl,
                "tsb": r.tsb,
                "tss_atl": getattr(r, "tss_atl", None),
                "tss_ctl": getattr(r, "tss_ctl", None),
                "tss_tsb": getattr(r, "tss_tsb", None),
            }
            for r in rows
        ]
    finally:
        session.close()


def get_current_training_load():
    rows = get_training_load(42)
    if not rows:
        return {"error": "No training-load history. Run build_training_load first."}
    latest = rows[-1]
    last_7 = rows[-7:]
    last_28 = rows[-28:]
    return {
        "date": latest["date"],
        "current": latest,
        "balance_models": {
            "garmin_native": {"atl": latest.get("atl"), "ctl": latest.get("ctl"), "tsb": latest.get("tsb")},
            "tss_derived": {"atl": latest.get("tss_atl"), "ctl": latest.get("tss_ctl"), "tsb": latest.get("tss_tsb")},
        },
        "last_7_days": {
            "garmin_load": sum((r["garmin_load"] or 0) for r in last_7),
            "tss": sum((r["tss"] or 0) for r in last_7) if any(r["tss"] is not None for r in last_7) else None,
            "duration_hours": sum(r["duration_hours"] for r in last_7),
        },
        "last_28_days": {
            "garmin_load": sum((r["garmin_load"] or 0) for r in last_28),
            "tss": sum((r["tss"] or 0) for r in last_28) if any(r["tss"] is not None for r in last_28) else None,
            "duration_hours": sum(r["duration_hours"] for r in last_28),
        },
    }
