from datetime import timedelta

from analytics import (
    get_health_history,
    get_activity_history,
)


def analyze_workout_recovery(days=14):

    health = get_health_history(days)
    activities = get_activity_history(days)

    health = sorted(
        health,
        key=lambda x: x.date
    )

    activities = sorted(
        activities,
        key=lambda x: x.activity_date
    )

    results = []

    for i, day in enumerate(health):

        # Find workouts on this day
        day_activities = [
            activity
            for activity in activities
            if activity.activity_date == day.date
        ]

        total_load = sum(
            activity.training_load or 0
            for activity in day_activities
        )

        total_duration = sum(
            activity.duration_seconds or 0
            for activity in day_activities
        )

        # Look at the following day
        next_day = None

        if i + 1 < len(health):
            next_day = health[i + 1]

        recovery_change = None

        if next_day:

            if (
                day.hrv is not None
                and next_day.hrv is not None
            ):

                recovery_change = (
                    next_day.hrv - day.hrv
                ) / day.hrv * 100

        results.append({
            "date": day.date,
            "activities": len(day_activities),
            "training_load": total_load,
            "duration_hours":
                total_duration / 3600,
            "hrv": day.hrv,
            "next_day_hrv_change":
                recovery_change,
            "readiness": day.training_readiness,
        })

    return results