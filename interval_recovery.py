"""Detailed bike/run interval recovery analysis using Garmin samples and lap summaries."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from activity_details import parse_activity_details
from garmin_client import GarminClient
from coaching_tables import get_treadmill_intervals


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _timestamp(v, relative_to=None):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        if x > 10_000_000_000:
            x /= 1000
        if x < 1_000_000 and relative_to is not None:
            from datetime import timedelta
            return relative_to + timedelta(seconds=x)
        try:
            return datetime.fromtimestamp(x, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            try:
                return _timestamp(float(s), relative_to=relative_to)
            except ValueError:
                return None
    return None


def _lap_time_bounds(lap: dict[str, Any]):
    start = None
    end = None
    for key in ("startTimeGMT", "startTime", "startTimestamp", "startTimeLocal"):
        start = _timestamp(lap.get(key))
        if start:
            break
    for key in ("endTimeGMT", "endTime", "endTimestamp", "endTimeLocal"):
        end = _timestamp(lap.get(key))
        if end:
            break
    return start, end


def _sample_hr(sample: dict[str, Any]):
    for key in ("directHeartRate", "heartRate", "averageHR", "avgHR", "heartRateValue"):
        v = _num(sample.get(key))
        if v is not None and 25 <= v <= 240:
            return v
    return None


def _sample_cadence(sample: dict[str, Any], sport: str):
    keys = ("directRunCadence", "runCadence", "cadence", "directCadence", "stepsPerMinute") if sport == "run" else ("directBikeCadence", "bikeCadence", "cadence", "directCadence")
    for key in keys:
        v = _num(sample.get(key))
        if v is not None and 40 <= v <= 260:
            return v
    return None


def _sample_power(sample: dict[str, Any]):
    for key in ("directPower", "power", "watts", "powerWatts"):
        v = _num(sample.get(key))
        if v is not None and 0 <= v <= 2500:
            return v
    return None


def _sample_speed(sample: dict[str, Any]):
    for key in ("directSpeed", "speed", "averageSpeed"):
        v = _num(sample.get(key))
        if v is not None and v > 0:
            return v
    return None


def _pace_from_mps(mps):
    # Reference only for treadmill: Garmin speed/pace is intentionally not
    # treated as valid objective treadmill pace in the coaching system.
    if mps is None or mps <= 0:
        return None
    sec_per_mile = 1609.344 / mps
    minutes = int(sec_per_mile // 60)
    seconds = int(round(sec_per_mile - minutes * 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}/mi"


def _mean(values):
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def _lap_metric(lap, keys):
    for key in keys:
        value = _num(lap.get(key))
        if value is not None:
            return value
    return None


def _activity_time_anchor(laps):
    for lap in laps:
        for key in ("startTimeGMT", "startTime", "startTimestamp", "startTimeLocal"):
            anchor = _timestamp(lap.get(key))
            if anchor:
                return anchor
    return None


def analyze_interval_recovery(
    activity_id: int,
    sport: str,
    work_lap_indices: list[int],
    recovery_lap_indices: list[int],
    manual_work_target_paces: list[str] | None = None,
) -> dict:
    """Analyze bike/run recovery laps using detailed Garmin samples.

    Lap indices are 1-based. Detailed HR samples are used to calculate the true
    minimum HR when lap timestamps are available. Treadmill pace remains manual;
    bike/run power and cadence are derived from Garmin data when available.
    """
    sport = sport.lower().strip()
    if sport not in {"bike", "run"}:
        return {"error": "sport must be bike or run"}
    if len(work_lap_indices) != len(recovery_lap_indices):
        return {"error": "work_lap_indices and recovery_lap_indices must have the same length."}

    # If manual treadmill paces were previously saved for this activity,
    # load them automatically. An explicitly supplied manual_work_target_paces
    # argument still takes precedence.
    if manual_work_target_paces is None and sport == "run":
        try:
            saved = get_treadmill_intervals(activity_id) or {}
            saved_intervals = saved.get("manual_treadmill_intervals") or []
            extracted = []
            for item in saved_intervals:
                if not isinstance(item, dict):
                    extracted.append(None)
                    continue
                pace = None
                for key in (
                    "pace", "manual_pace", "target_pace", "pace_per_mile",
                    "pace_per_mi", "actual_pace", "reported_pace",
                ):
                    value = item.get(key)
                    if value is not None and str(value).strip():
                        pace = str(value).strip()
                        break
                extracted.append(pace)
            if extracted and any(v is not None for v in extracted):
                manual_work_target_paces = extracted
        except Exception:
            # Manual annotations must never prevent Garmin interval analysis.
            pass

    garmin = GarminClient()
    garmin.login()
    splits = garmin.get_activity_splits(activity_id)
    laps = splits.get("lapDTOs", [])
    details = garmin.get_activity_details(activity_id)
    samples = parse_activity_details(details)
    activity_anchor = _activity_time_anchor(laps)

    def get_lap(index):
        if index < 1 or index > len(laps):
            return None
        return laps[index - 1]

    def _sample_timestamp(sample):
        raw_ts = sample.get("timestamp") or sample.get("directTimestamp")
        return _timestamp(raw_ts, relative_to=activity_anchor)

    sample_times = [_sample_timestamp(s) for s in samples]

    def samples_for_lap(lap_index, lap):
        # Primary path: direct absolute timestamp matching.
        start, end = _lap_time_bounds(lap)
        if start and end:
            out = [
                sample
                for sample, ts in zip(samples, sample_times)
                if ts and start <= ts <= end
            ]
            if out:
                return out

        # Fallback: map detail samples to laps by elapsed time using the
        # cumulative Garmin lap durations. This handles Garmin detail streams
        # whose timestamp representation differs from lapDTO timestamps.
        valid_times = [ts for ts in sample_times if ts is not None]
        if not valid_times:
            return []

        first_ts = valid_times[0]
        sample_elapsed = [
            (ts - first_ts).total_seconds() if ts is not None else None
            for ts in sample_times
        ]

        lap_durations = []
        for item in laps:
            duration = _num(item.get("duration") or item.get("durationSeconds"))
            if duration is None:
                ls, le = _lap_time_bounds(item)
                if ls and le:
                    duration = (le - ls).total_seconds()
            lap_durations.append(duration)

        if any(d is None or d <= 0 for d in lap_durations):
            return []

        lap_start_elapsed = sum(lap_durations[:lap_index - 1])
        lap_end_elapsed = lap_start_elapsed + lap_durations[lap_index - 1]

        return [
            sample
            for sample, elapsed in zip(samples, sample_elapsed)
            if elapsed is not None
            and lap_start_elapsed <= elapsed <= lap_end_elapsed
        ]

    results = []
    for rep, (wi, ri) in enumerate(zip(work_lap_indices, recovery_lap_indices), start=1):
        work = get_lap(wi)
        recovery = get_lap(ri)
        if not work or not recovery:
            results.append({"rep": rep, "work_lap": wi, "recovery_lap": ri, "error": "Lap index not found."})
            continue

        recovery_samples = samples_for_lap(ri, recovery)
        work_samples = samples_for_lap(wi, work)
        recovery_hr = [_sample_hr(s) for s in recovery_samples]
        work_hr = [_sample_hr(s) for s in work_samples]
        recovery_cadence = [_sample_cadence(s, sport) for s in recovery_samples]
        work_cadence = [_sample_cadence(s, sport) for s in work_samples]
        recovery_power = [_sample_power(s) for s in recovery_samples]
        work_power = [_sample_power(s) for s in work_samples]
        recovery_speed = [_sample_speed(s) for s in recovery_samples]

        work_max_hr = _num(work.get("maxHR") or work.get("maxHeartRate") or work.get("maximumHR"))
        if work_max_hr is None and work_hr:
            work_max_hr = max(work_hr)
        recovery_max_hr = _num(recovery.get("maxHR") or recovery.get("maxHeartRate") or recovery.get("maximumHR"))
        recovery_avg_hr = _num(recovery.get("averageHR") or recovery.get("avgHR") or recovery.get("averageHeartRate"))
        recovery_min_hr = min(recovery_hr) if recovery_hr else None
        recovery_start_hr = recovery_hr[0] if recovery_hr else recovery_max_hr

        duration = _num(recovery.get("duration") or recovery.get("durationSeconds"))
        if duration is None:
            rs, re = _lap_time_bounds(recovery)
            if rs and re:
                duration = (re - rs).total_seconds()

        max_to_min = round(work_max_hr - recovery_min_hr, 2) if work_max_hr is not None and recovery_min_hr is not None else None
        start_to_min = round(recovery_start_hr - recovery_min_hr, 2) if recovery_start_hr is not None and recovery_min_hr is not None else None
        recovery_rate = round(start_to_min / (duration / 60), 2) if start_to_min is not None and duration and duration > 0 else None

        cadence_keys = ("averageRunCadence", "avgRunCadence", "averageCadence") if sport == "run" else ("averageBikeCadence", "avgBikeCadence", "averageCadence")
        work_avg_cad = next((_num(work.get(k)) for k in cadence_keys if _num(work.get(k)) is not None), None)
        recovery_avg_cad = next((_num(recovery.get(k)) for k in cadence_keys if _num(recovery.get(k)) is not None), None)
        if recovery_avg_cad is None:
            recovery_avg_cad = _mean(recovery_cadence)
        if work_avg_cad is None:
            work_avg_cad = _mean(work_cadence)

        # For cycling, use Garmin's lap-summary averagePower as the canonical
        # work/recovery power. Detailed samples can cover a slightly different
        # sub-window, which should not silently replace the lap statistic.
        if sport == "bike":
            work_avg_power = _lap_metric(
                work,
                ("averagePower", "avgPower", "power", "averageWatts", "avgWatts", "watts"),
            )
            recovery_avg_power = _lap_metric(
                recovery,
                ("averagePower", "avgPower", "power", "averageWatts", "avgWatts", "watts"),
            )
            if work_avg_power is None:
                work_avg_power = _mean(work_power)
            if recovery_avg_power is None:
                recovery_avg_power = _mean(recovery_power)
        else:
            work_avg_power = _mean(work_power)
            recovery_avg_power = _mean(recovery_power)
            if work_avg_power is None:
                work_avg_power = _lap_metric(
                    work,
                    ("averagePower", "avgPower", "power", "averageWatts", "avgWatts", "watts"),
                )
            if recovery_avg_power is None:
                recovery_avg_power = _lap_metric(
                    recovery,
                    ("averagePower", "avgPower", "power", "averageWatts", "avgWatts", "watts"),
                )

        garmin_speed = _mean(recovery_speed)
        if garmin_speed is None:
            garmin_speed = _lap_metric(
                recovery,
                ("averageSpeed", "avgSpeed", "speed", "averageSpeedMetersPerSecond"),
            )

        manual_work_target_pace = (
            manual_work_target_paces[rep - 1]
            if manual_work_target_paces and rep - 1 < len(manual_work_target_paces)
            else None
        )

        results.append({
            "rep": rep,
            "work_lap": wi,
            "recovery_lap": ri,
            "work_max_hr_bpm": round(work_max_hr, 1) if work_max_hr is not None else None,
            "recovery_hr_start_bpm": round(recovery_start_hr, 1) if recovery_start_hr is not None else None,
            "recovery_hr_min_bpm": round(recovery_min_hr, 1) if recovery_min_hr is not None else None,
            "recovery_hr_avg_bpm": round(recovery_avg_hr, 1) if recovery_avg_hr is not None else None,
            "recovery_hr_max_bpm": round(recovery_max_hr, 1) if recovery_max_hr is not None else None,
            "hr_drop_work_max_to_recovery_min_bpm": max_to_min,
            "hr_drop_recovery_start_to_min_bpm": start_to_min,
            "hr_recovery_rate_bpm_per_min": recovery_rate,
            "work_avg_cadence": round(work_avg_cad, 1) if work_avg_cad is not None else None,
            "recovery_avg_cadence": round(recovery_avg_cad, 1) if recovery_avg_cad is not None else None,
            "cadence_unit": "spm" if sport == "run" else "rpm",
            "cadence_drop": round(work_avg_cad - recovery_avg_cad, 1) if work_avg_cad is not None and recovery_avg_cad is not None else None,
            "work_avg_power_w": round(work_avg_power, 1) if work_avg_power is not None else None,
            "recovery_avg_power_w": round(recovery_avg_power, 1) if recovery_avg_power is not None else None,
            "power_drop_w": round(work_avg_power - recovery_avg_power, 1) if work_avg_power is not None and recovery_avg_power is not None else None,
            "recovery_duration_seconds": round(duration, 1) if duration is not None else None,
            "hr_min_source": "detailed_garmin_hr_samples" if recovery_min_hr is not None else "unavailable",
            **(
                {
                    "manual_work_target_pace": manual_work_target_pace,
                    "garmin_recovery_speed_mps_reference_only": round(garmin_speed, 3) if garmin_speed is not None else None,
                    "garmin_recovery_pace_reference_only": _pace_from_mps(garmin_speed),
                    "pace_source": "manual" if manual_work_target_pace else "garmin_reference_only",
                }
                if sport == "run"
                else {}
            ),
        })

    response = {
        "activity_id": activity_id,
        "sport": sport,
        "analysis_type": f"{sport}_interval_recovery",
        "lap_indices_are_1_based": True,
        "hr_min_note": "Recovery minimum HR is calculated from detailed Garmin HR samples when timestamps map to the selected recovery laps.",
        "recovery_analysis": results,
    }

    if sport == "run":
        response["pace_warning"] = (
            "For treadmill runs, Garmin treadmill speed/pace is reference-only; "
            "use manually reported treadmill pace as the authoritative pace. "
            "For non-treadmill runs, Garmin pace remains objective."
        )
    else:
        response["pace_note"] = "Bike recovery speed is informational; power is the primary output metric."

    return response
