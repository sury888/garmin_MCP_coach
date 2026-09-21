from analytics import get_health_history
from trends import analyze_today
from workout_relationships import analyze_workout_recovery


def calculate_recovery_score():

    health = get_health_history(30)

    if not health:
        return None

    today = health[-1]

    score = 100
    reasons = []

    # =========================================================
    # HRV
    # =========================================================

    if today.hrv is not None:

        hrv_values = [
            x.hrv
            for x in health
            if x.hrv is not None
        ]

        if hrv_values:
            baseline = sum(hrv_values) / len(hrv_values)

            deviation = (
                (today.hrv - baseline)
                / baseline
            ) * 100

            if deviation <= -20:
                score -= 25
                reasons.append(
                    f"HRV is {abs(deviation):.1f}% below baseline"
                )

            elif deviation <= -10:
                score -= 15
                reasons.append(
                    f"HRV is {abs(deviation):.1f}% below baseline"
                )

            elif deviation < 0:
                score -= 5

    # =========================================================
    # RESTING HEART RATE
    # =========================================================

    if today.resting_hr is not None:

        rhr_values = [
            x.resting_hr
            for x in health
            if x.resting_hr is not None
        ]

        if rhr_values:
            baseline = sum(rhr_values) / len(rhr_values)

            difference = today.resting_hr - baseline

            if difference >= 5:
                score -= 20
                reasons.append(
                    f"Resting HR is {difference:.1f} bpm above baseline"
                )

            elif difference >= 3:
                score -= 10
                reasons.append(
                    f"Resting HR is {difference:.1f} bpm above baseline"
                )

    # =========================================================
    # SLEEP
    # =========================================================

    if today.sleep_hours is not None:

        sleep_values = [
            x.sleep_hours
            for x in health
            if x.sleep_hours is not None
        ]

        if sleep_values:
            baseline = sum(sleep_values) / len(sleep_values)

            difference = today.sleep_hours - baseline

            if difference <= -1.5:
                score -= 20
                reasons.append(
                    f"Sleep was {abs(difference):.1f} hours below baseline"
                )

            elif difference <= -0.75:
                score -= 10
                reasons.append(
                    f"Sleep was {abs(difference):.1f} hours below baseline"
                )

    # =========================================================
    # BODY BATTERY
    # =========================================================

    if today.body_battery is not None:

        battery_values = [
            x.body_battery
            for x in health
            if x.body_battery is not None
        ]

        if battery_values:
            baseline = sum(battery_values) / len(battery_values)

            difference = today.body_battery - baseline

            if difference <= -20:
                score -= 15
                reasons.append(
                    "Body Battery is significantly below baseline"
                )

            elif difference <= -10:
                score -= 8

    # =========================================================
    # ACWR
    # =========================================================

    if today.acwr is not None:

        if today.acwr >= 1.3:
            score -= 15
            reasons.append(
                f"ACWR is elevated at {today.acwr:.2f}"
            )

        elif today.acwr >= 1.1:
            score -= 5

    # =========================================================
    # SCORE / CLASSIFICATION
    # =========================================================

    score = max(0, min(100, score))

    if score >= 80:
        status = "EXCELLENT"
    elif score >= 65:
        status = "GOOD"
    elif score >= 50:
        status = "MODERATE"
    elif score >= 35:
        status = "POOR"
    else:
        status = "VERY POOR"

    return {
        "date": today.date,
        "score": score,
        "status": status,
        "reasons": reasons,
    }
def generate_adjusted_workout(
    planned_workout,
    planned_duration_minutes,
    planned_intensity,
    sport,
    coaching_context=None,
    recovery_score=None,
    recovery_status=None,
    health_trend=None
):
    """
    Generate a modified workout based on athlete recovery
    and coaching context.
    """

    # Pull values from coaching context when provided
    if coaching_context:

        recovery = coaching_context.get("recovery", {})

        recovery_score = recovery.get(
            "score",
            recovery_score
        )

        recovery_status = recovery.get(
            "status",
            recovery_status
        )

        health_trend = coaching_context.get(
            "health_trends",
            {}
        ).get(
            "overall_recovery_trend",
            health_trend
        )

    # ---------------------------------------------------------
    # VERY POOR RECOVERY
    # ---------------------------------------------------------

    if recovery_score is not None and recovery_score < 35:

        return {
            "decision": "REPLACE",

            "original_workout": {
                "sport": sport,
                "workout": planned_workout,
                "duration_minutes": planned_duration_minutes,
                "intensity": planned_intensity
            },

            "adjusted_workout": {
                "sport": (
                    "easy_cycling"
                    if sport == "cycling"
                    else "easy_swimming"
                ),
                "workout": "Easy aerobic recovery session",
                "duration_minutes": 30,
                "intensity": "VERY EASY",
                "target": "Conversational effort / Zone 1-2",
                "structure": (
                    "10 min easy warm-up + "
                    "15 min easy aerobic + "
                    "5 min easy cooldown"
                )
            },

            "reason": (
                "Recovery is very poor. Replace the planned "
                "high-intensity workout with an easy recovery session."
            ),

            "recovery_score": recovery_score,
            "recovery_status": recovery_status,
            "health_trend": health_trend
        }

    # ---------------------------------------------------------
    # POOR RECOVERY
    # ---------------------------------------------------------

    elif recovery_score is not None and recovery_score < 50:

        return {
            "decision": "MODIFY",

            "original_workout": {
                "sport": sport,
                "workout": planned_workout,
                "duration_minutes": planned_duration_minutes,
                "intensity": planned_intensity
            },

            "adjusted_workout": {
                "sport": sport,
                "workout": "Reduced aerobic endurance session",
                "duration_minutes": min(
                    60,
                    planned_duration_minutes
                ),
                "intensity": "EASY",
                "target": "Zone 1-2",
                "structure": (
                    "Steady aerobic effort with "
                    "no intervals"
                )
            },

            "reason": (
                "Recovery is poor. Reduce duration "
                "and remove high-intensity work."
            ),

            "recovery_score": recovery_score,
            "recovery_status": recovery_status,
            "health_trend": health_trend
        }

    # ---------------------------------------------------------
    # MODERATE RECOVERY
    # ---------------------------------------------------------

    elif recovery_score is not None and recovery_score < 65:

        return {
            "decision": "MODIFY",

            "original_workout": {
                "sport": sport,
                "workout": planned_workout,
                "duration_minutes": planned_duration_minutes,
                "intensity": planned_intensity
            },

            "adjusted_workout": {
                "sport": sport,
                "workout": "Reduced planned workout",
                "duration_minutes": round(
                    planned_duration_minutes * 0.75
                ),
                "intensity": "MODERATE",
                "target": (
                    "Mostly Zone 2 with "
                    "limited moderate work"
                ),
                "structure": (
                    "Reduce interval volume "
                    "by approximately 25%"
                )
            },

            "reason": (
                "Recovery is moderate. Maintain training "
                "stimulus while reducing overall stress."
            ),

            "recovery_score": recovery_score,
            "recovery_status": recovery_status,
            "health_trend": health_trend
        }

    # ---------------------------------------------------------
    # GOOD / EXCELLENT RECOVERY
    # ---------------------------------------------------------

    else:

        return {
            "decision": "KEEP",

            "original_workout": {
                "sport": sport,
                "workout": planned_workout,
                "duration_minutes": planned_duration_minutes,
                "intensity": planned_intensity
            },

            "adjusted_workout": {
                "sport": sport,
                "workout": planned_workout,
                "duration_minutes": planned_duration_minutes,
                "intensity": planned_intensity
            },

            "reason": (
                "Recovery is sufficient to complete "
                "the planned workout."
            ),

            "recovery_score": recovery_score,
            "recovery_status": recovery_status,
            "health_trend": health_trend
        }

def generate_coaching_analysis():

    health = get_health_history(30)

    if not health:
        return None

    today = health[-1]

    # =========================================================
    # MULTI-DAY TRENDS
    # =========================================================

    from health_trends import get_health_trends

    raw_trends = get_health_trends(30)

    # Normalize health trend output to the structure expected
    # by the coaching layer.
    trends = raw_trends

    if isinstance(raw_trends, dict):

        trend_data = raw_trends.get("trends", raw_trends)

        if isinstance(trend_data, dict):

            normalized_trends = {}

            for metric, trend in trend_data.items():

                if not isinstance(trend, dict):
                    continue

                normalized = dict(trend)

                # health_trends.py uses "change_percent"
                # while the coaching layer uses
                # "overall_change_percent".
                if "overall_change_percent" not in normalized:

                    normalized["overall_change_percent"] = normalized.get(
                        "change_percent"
                    )

                # Ensure consecutive trend fields exist.
                normalized.setdefault("consecutive_up", 0)
                normalized.setdefault("consecutive_down", 0)

                normalized_trends[metric] = normalized

            trends = {
                "days_analyzed": raw_trends.get("days_analyzed"),
                "first_half_days": raw_trends.get("first_half_days"),
                "second_half_days": raw_trends.get("second_half_days"),
                "trends": normalized_trends,
            }


    # =========================================================
    # RECOVERY SCORE
    # =========================================================

    recovery = calculate_recovery_score()

    # =========================================================
    # WORKOUT → RECOVERY
    # =========================================================

    try:
        workout_analysis = analyze_workout_recovery(14)
    except TypeError:
        workout_analysis = analyze_workout_recovery()

    # Handle either dictionary or list output
    if isinstance(workout_analysis, dict):
        observations = workout_analysis.get("observations", [])
    else:
        observations = workout_analysis

    hrv_responses = []

    if isinstance(observations, list):

        for observation in observations:

            if not isinstance(observation, dict):
                continue

            change = observation.get("next_day_hrv_change")

            if change is not None:
                hrv_responses.append(change)

    average_hrv_response = None

    if hrv_responses:
        average_hrv_response = (
            sum(hrv_responses) / len(hrv_responses)
        )

    # =========================================================
    # COACHING SIGNALS
    # =========================================================

    coaching_signals = []

    if isinstance(trends, dict):

        trend_data = trends.get("trends", trends)

        if isinstance(trend_data, dict):

            hrv = trend_data.get("hrv")

            if hrv and hrv.get("direction") == "decreasing":
                coaching_signals.append(
                    "HRV has declined significantly over the period."
                )

            rhr = trend_data.get("resting_hr")

            if rhr and rhr.get("direction") == "increasing":
                coaching_signals.append(
                    "Resting HR has increased significantly."
                )

            sleep = trend_data.get("sleep_hours")

            if sleep and sleep.get("direction") == "decreasing":
                coaching_signals.append(
                    "Average sleep duration has decreased."
                )

            battery = trend_data.get("body_battery")

            if battery and battery.get("direction") == "decreasing":
                coaching_signals.append(
                    "Average Body Battery has declined."
                )

    # =========================================================
    # COACH ASSESSMENT
    # =========================================================

    if recovery["score"] < 35:

        assessment = (
            "Recovery is very poor. Multiple recovery markers are "
            "unfavorable, suggesting substantial accumulated fatigue."
        )

        recommendation = (
            "Prioritize recovery today. Keep training easy and avoid "
            "stacking another high-intensity session unless there is "
            "a specific reason to do so."
        )

    elif recovery["score"] < 50:

        assessment = (
            "Recovery is poor. Several recovery markers are unfavorable "
            "and training load should be managed carefully."
        )

        recommendation = (
            "Keep today's training controlled and avoid unnecessary "
            "high-intensity work."
        )

    elif recovery["score"] < 65:

        assessment = (
            "Recovery is moderate. Some fatigue signals are present, "
            "but controlled training may still be appropriate."
        )

        recommendation = (
            "Use workout execution and recent training load to determine "
            "whether intensity is appropriate."
        )

    else:

        assessment = (
            "Recovery is generally favorable with no major negative "
            "recovery signals."
        )

        recommendation = (
            "Training can proceed as planned while continuing to "
            "monitor recovery trends."
        )

    # =========================================================
    # RETURN STRUCTURE
    # =========================================================

    return {
        "date": today.date,

        "trends": trends,

        "recovery": recovery,

        "signals": coaching_signals,

        "workout_recovery": {
            "average_next_day_hrv_change": average_hrv_response,
            "observations": len(hrv_responses),
        },

        "assessment": assessment,

        "recommendation": recommendation,
    }


def main():

    result = generate_coaching_analysis()

    print("=" * 70)
    print("GARMIN COACH — TREND ANALYSIS")
    print("=" * 70)

    if not result:
        print("\nNo data available.")
        return

    print(f"\nDate: {result['date']}")

    recovery = result["recovery"]

    print("\nRECOVERY")
    print("-" * 70)
    print(f"Score: {recovery['score']}/100")
    print(f"Status: {recovery['status']}")

    print("\nReasons")

    if recovery["reasons"]:
        for reason in recovery["reasons"]:
            print(f"• {reason}")
    else:
        print("No significant negative recovery signals.")

    workout = result["workout_recovery"]

    print("\nWORKOUT → RECOVERY")
    print("-" * 70)

    if workout["average_next_day_hrv_change"] is not None:
        print(
            f"Average next-day HRV response: "
            f"{workout['average_next_day_hrv_change']:.1f}%"
        )

    print(f"Observations: {workout['observations']}")

    print("\nCOACH ASSESSMENT")
    print("-" * 70)
    print(result["assessment"])

    print("\nRECOMMENDATION")
    print("-" * 70)
    print(result["recommendation"])


def analyze_workout_response(coaching_context):
    """
    Analyze how recent training has affected recovery.
    """

    workout_recovery = coaching_context.get(
        "workout_recovery",
        []
    )

    if not workout_recovery:
        return {
            "available": False,
            "message": "Not enough workout-response data."
        }

    responses = []

    for workout in workout_recovery:

        next_day_change = workout.get(
            "next_day_hrv_change"
        )

        if next_day_change is None:
            continue

        responses.append({
            "date": workout.get("date"),
            "training_load": workout.get("training_load"),
            "duration_hours": workout.get("duration_hours"),
            "hrv_change_next_day": next_day_change,
            "readiness": workout.get("readiness")
        })

    if not responses:
        return {
            "available": False,
            "message": "No next-day recovery responses available."
        }

    average_hrv_change = (
        sum(
            x["hrv_change_next_day"]
            for x in responses
        )
        / len(responses)
    )

    high_load_responses = [
        x for x in responses
        if x["training_load"] >= 200
    ]

    high_load_hrv_change = None

    if high_load_responses:
        high_load_hrv_change = (
            sum(
                x["hrv_change_next_day"]
                for x in high_load_responses
            )
            / len(high_load_responses)
        )

    signals = []

    if average_hrv_change <= -3:
        signals.append(
            "Recent training is associated with meaningful next-day HRV suppression."
        )

    if high_load_hrv_change is not None and high_load_hrv_change <= -3:
        signals.append(
            "Higher-load sessions appear to produce a stronger negative HRV response."
        )

    return {
        "available": True,
        "observations": len(responses),
        "average_next_day_hrv_change_percent": round(
            average_hrv_change,
            2
        ),
        "high_load_observations": len(
            high_load_responses
        ),
        "high_load_average_hrv_change_percent": (
            round(high_load_hrv_change, 2)
            if high_load_hrv_change is not None
            else None
        ),
        "signals": signals,
        "responses": responses
    }

if __name__ == "__main__":
    main()

