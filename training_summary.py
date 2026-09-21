from analytics import get_activity_history


def get_training_summary(days: int = 7) -> dict:
    """
    Summarize training over the last N days.

    Returns total activities, duration, distance, training load,
    average daily load, and breakdown by sport.
    """

    activities = get_activity_history(days)

    if not activities:
        return {
            "days": days,
            "activities": 0,
            "total_duration_hours": 0,
            "total_distance_km": 0,
            "total_training_load": 0,
            "average_daily_load": 0,
            "by_sport": {}
        }

    total_duration = 0
    total_distance = 0
    total_load = 0

    by_sport = {}

    for activity in activities:

        duration = activity.duration_seconds or 0
        distance = activity.distance_meters or 0
        load = activity.training_load or 0

        total_duration += duration
        total_distance += distance
        total_load += load

        sport = activity.activity_type or "unknown"

        if sport not in by_sport:
            by_sport[sport] = {
                "activities": 0,
                "duration_hours": 0,
                "distance_km": 0,
                "training_load": 0
            }

        by_sport[sport]["activities"] += 1
        by_sport[sport]["duration_hours"] += duration / 3600
        by_sport[sport]["distance_km"] += distance / 1000
        by_sport[sport]["training_load"] += load

    return {
        "days": days,
        "activities": len(activities),

        "total_duration_hours":
            total_duration / 3600,

        "total_distance_km":
            total_distance / 1000,

        "total_training_load":
            total_load,

        "average_daily_load":
            total_load / days,

        "by_sport": by_sport
    }