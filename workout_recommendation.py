from recommendations import get_workout_recommendation


def evaluate_planned_workout(
    sport: str,
    planned_duration_minutes: int,
    planned_intensity: str,
    planned_workout: str
) -> dict:

    recommendation = get_workout_recommendation()

    if "error" in recommendation:
        return recommendation

    score = recommendation["recovery_score"]
    recovery_status = recommendation["recovery_status"]
    health_trend = recommendation["health_trend"]

    intensity = planned_intensity.upper()

    decision = "KEEP"
    modified_duration = planned_duration_minutes
    modified_intensity = planned_intensity
    reason = "Recovery metrics support completing the planned workout."

    # ---------------------------------------------------------
    # VERY POOR RECOVERY
    # ---------------------------------------------------------

    if score < 35:

        if intensity in [
            "VO2",
            "VO2_MAX",
            "THRESHOLD",
            "RACE_PACE",
            "INTERVALS",
            "HIGH"
        ]:

            decision = "REPLACE"
            modified_duration = 30
            modified_intensity = "VERY EASY"
            reason = (
                "Recovery is very poor and the planned workout "
                "contains high-intensity work."
            )

        elif planned_duration_minutes >= 75:

            decision = "MODIFY"
            modified_duration = 45
            modified_intensity = "EASY"
            reason = (
                "Recovery is very poor and the planned session "
                "is too long for the current recovery state."
            )

        else:

            decision = "MODIFY"
            modified_duration = min(planned_duration_minutes, 60)
            modified_intensity = "EASY"
            reason = (
                "Recovery is very poor. Keep the session short "
                "and easy."
            )

    # ---------------------------------------------------------
    # POOR RECOVERY
    # ---------------------------------------------------------

    elif score < 50:

        if intensity in [
            "VO2",
            "VO2_MAX",
            "THRESHOLD",
            "RACE_PACE",
            "INTERVALS",
            "HIGH"
        ]:

            decision = "MODIFY"
            modified_duration = 45
            modified_intensity = "EASY"
            reason = (
                "Recovery is poor, so high-intensity training "
                "should be replaced with easy aerobic work."
            )

        elif planned_duration_minutes > 90:

            decision = "MODIFY"
            modified_duration = 60
            modified_intensity = "EASY"
            reason = (
                "Recovery is poor and the planned duration "
                "should be reduced."
            )

    # ---------------------------------------------------------
    # MODERATE RECOVERY
    # ---------------------------------------------------------

    elif score < 65:

        if intensity in [
            "VO2",
            "VO2_MAX",
            "THRESHOLD",
            "RACE_PACE",
            "HIGH"
        ]:

            decision = "MODIFY"
            modified_duration = max(
                45,
                int(planned_duration_minutes * 0.75)
            )
            modified_intensity = "MODERATE"
            reason = (
                "Recovery is moderate. Reduce the intensity "
                "and volume of the planned session."
            )

    # ---------------------------------------------------------
    # DECLINING TREND
    # ---------------------------------------------------------

    if health_trend == "declining_recovery" and decision == "KEEP":

        decision = "MODIFY"

        modified_duration = min(
            planned_duration_minutes,
            75
        )

        modified_intensity = "EASY_TO_MODERATE"

        reason = (
            "Recovery is currently acceptable, but the longer-term "
            "recovery trend is declining."
        )

    return {
        "decision": decision,
        "sport": sport,
        "planned_workout": planned_workout,
        "planned_duration_minutes": planned_duration_minutes,
        "planned_intensity": planned_intensity,
        "recommended_duration_minutes": modified_duration,
        "recommended_intensity": modified_intensity,
        "recovery_score": score,
        "recovery_status": recovery_status,
        "health_trend": health_trend,
        "reason": reason
    }