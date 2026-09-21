from analytics import generate_coaching_context


def get_workout_recommendation(
    days: int = 7,
    baseline_days: int = 30
) -> dict:

    context = generate_coaching_context(
        days=days,
        baseline_days=baseline_days
    )

    if not context:
        return {
            "error": "Not enough data to generate workout recommendation."
        }

    recovery = context["recovery"]
    health_trend = context["health_trends"]["overall_recovery_trend"]
    flags = context["key_flags"]

    score = recovery["score"]
    status = recovery["status"]

    # ---------------------------------------------------------
    # DECISION ENGINE
    # ---------------------------------------------------------

    recommendation = "NORMAL_TRAINING"
    intensity = "MODERATE"
    duration = "NORMAL"
    allowed_sports = [
        "cycling",
        "running",
        "swimming"
    ]
    avoid = []

    # VERY POOR RECOVERY
    if score < 35:

        recommendation = "RECOVERY"
        intensity = "VERY EASY"
        duration = "30-60 minutes"

        allowed_sports = [
            "easy_cycling",
            "easy_swimming",
            "walking"
        ]

        avoid = [
            "hard intervals",
            "threshold work",
            "VO2 max work",
            "long endurance session",
            "hard running",
            "race-pace work"
        ]

    # POOR RECOVERY
    elif score < 50:

        recommendation = "EASY_TRAINING"
        intensity = "EASY"
        duration = "45-75 minutes"

        allowed_sports = [
            "easy_cycling",
            "easy_swimming",
            "easy_running"
        ]

        avoid = [
            "VO2 max intervals",
            "threshold work",
            "race-pace work"
        ]

    # MODERATE RECOVERY
    elif score < 65:

        recommendation = "MODIFIED_TRAINING"
        intensity = "EASY_TO_MODERATE"
        duration = "60-90 minutes"

        avoid = [
            "maximal efforts",
            "high-volume intensity"
        ]

    # GOOD / EXCELLENT
    else:

        recommendation = "NORMAL_TRAINING"
        intensity = "NORMAL"

    # ---------------------------------------------------------
    # ADDITIONAL SAFETY CHECKS
    # ---------------------------------------------------------

    if health_trend == "declining_recovery":

        if recommendation == "NORMAL_TRAINING":
            recommendation = "MODIFIED_TRAINING"

        avoid.append("stacking multiple high-intensity sessions")

    # Remove duplicates
    avoid = list(dict.fromkeys(avoid))

    # ---------------------------------------------------------
    # BUILD RESPONSE
    # ---------------------------------------------------------

    return {
        "date": context["date"],

        "recommendation": recommendation,

        "recovery_score": score,

        "recovery_status": status,

        "intensity": intensity,

        "duration": duration,

        "allowed_sports": allowed_sports,

        "avoid": avoid,

        "health_trend": health_trend,

        "reasoning": flags,

        "decision_basis": {
            "recovery_score": score,
            "recovery_status": status,
            "health_trend": health_trend,
            "key_flags": flags
        }
    }