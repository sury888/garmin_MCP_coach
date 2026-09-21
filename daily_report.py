from coach import calculate_recovery_score
from trends import analyze_today
from workout_relationships import analyze_workout_recovery
from analytics import get_activity_history
from coaching_workouts import build_today_workout_analysis


def generate_daily_report():

    recovery = calculate_recovery_score()
    today_analysis = analyze_today()
    workout_analysis = analyze_workout_recovery(7)
    today_workouts = build_today_workout_analysis()

    if not recovery or not today_analysis:
        return None

    # ---------------------------------------------------------
    # TODAY'S METRICS
    # ---------------------------------------------------------

    metrics = today_analysis["results"]

    # ---------------------------------------------------------
    # RECENT TRAINING
    # ---------------------------------------------------------

    recent_activities = get_activity_history(7)

    total_load = sum(
        activity.training_load or 0
        for activity in recent_activities
    )

    total_duration = sum(
        activity.duration_seconds or 0
        for activity in recent_activities
    )

    # ---------------------------------------------------------
    # TREND INFORMATION
    # ---------------------------------------------------------

        # ---------------------------------------------------------
    # TREND INFORMATION
    # ---------------------------------------------------------

    trend_data = {}

    if workout_analysis:

        hrv_changes = [
            x["next_day_hrv_change"]
            for x in workout_analysis
            if x["next_day_hrv_change"] is not None
        ]

        if hrv_changes:

            trend_data["hrv_response"] = {
                "average_next_day_change":
                    sum(hrv_changes) / len(hrv_changes),

                "observations":
                    len(hrv_changes),
            }

    # ---------------------------------------------------------
    # COACHING ASSESSMENT
    # ---------------------------------------------------------

    score = recovery["score"]

    if score < 25:

        assessment = (
            "Recovery is very poor. Multiple recovery markers "
            "are unfavorable, suggesting substantial accumulated "
            "fatigue."
        )

        recommendation = (
            "Prioritize recovery today. Keep training easy and "
            "avoid stacking another high-intensity session unless "
            "there is a specific reason to do so."
        )

    elif score < 40:

        assessment = (
            "Recovery is poor. There are several indicators of "
            "fatigue that should be considered when planning "
            "today's training."
        )

        recommendation = (
            "Favor lower-intensity aerobic work or recovery. "
            "Consider reducing volume or intensity."
        )

    elif score < 60:

        assessment = (
            "Recovery is moderate. Some fatigue signals are "
            "present, but recovery is not severely compromised."
        )

        recommendation = (
            "Training can continue, but monitor intensity and "
            "avoid unnecessary additional load."
        )

    elif score < 80:

        assessment = (
            "Recovery is good. Most recovery markers are within "
            "an acceptable range."
        )

        recommendation = (
            "Normal training is appropriate, while continuing "
            "to monitor recovery trends."
        )

    else:

        assessment = (
            "Recovery is excellent. Current recovery markers "
            "support productive training."
        )

        recommendation = (
            "Good conditions for normal or higher-quality "
            "training, assuming the planned session is "
            "appropriate for the current training block."
        )

    # ---------------------------------------------------------
    # REPORT
    # ---------------------------------------------------------

    return {
        "date": recovery["date"],

        "recovery": {
            "score": recovery["score"],
            "status": recovery["status"],
            "reasons": recovery["reasons"],
        },

        "metrics": metrics,

        "recent_training": {
            "activities": len(recent_activities),
            "duration_hours": total_duration / 3600,
            "training_load": total_load,
        },

        "trends": trend_data,

        "today_workouts": today_workouts,

        "assessment": assessment,

        "recommendation": recommendation,
    }


def print_daily_report():

    report = generate_daily_report()

    print("=" * 70)
    print("DAILY COACHING REPORT")
    print("=" * 70)

    if not report:
        print("Not enough data to generate report.")
        return

    print(f"\nDate: {report['date']}")

    # ---------------------------------------------------------
    # RECOVERY
    # ---------------------------------------------------------

    recovery = report["recovery"]

    print("\nRECOVERY")
    print("-" * 70)

    print(
        f"Score: {recovery['score']}/100"
    )

    print(
        f"Status: {recovery['status']}"
    )

    print("\nKey signals:")

    if recovery["reasons"]:

        for reason in recovery["reasons"]:
            print(f"⚠ {reason}")

    else:
        print("No significant negative recovery signals.")

    # ---------------------------------------------------------
    # RECENT TRAINING
    # ---------------------------------------------------------

    training = report["recent_training"]

    print("\nRECENT TRAINING — 7 DAYS")
    print("-" * 70)

    print(
        f"Activities: {training['activities']}"
    )

    print(
        f"Duration: {training['duration_hours']:.2f} hours"
    )

    print(
        f"Training load: {training['training_load']:.1f}"
    )

    # ---------------------------------------------------------
    # TRENDS
    # ---------------------------------------------------------

        # ---------------------------------------------------------
    # WORKOUT → RECOVERY
    # ---------------------------------------------------------

    print("\nWORKOUT → RECOVERY")
    print("-" * 70)

    hrv_response = report["trends"].get(
        "hrv_response"
    )

    if hrv_response:

        print(
            f"Average next-day HRV response: "
            f"{hrv_response['average_next_day_change']:+.1f}%"
        )

        print(
            f"Observations: "
            f"{hrv_response['observations']}"
        )

    else:

        print(
            "Not enough workout/recovery data."
        )
    # ---------------------------------------------------------
    # COACH ASSESSMENT
    # ---------------------------------------------------------

    print("\nCOACH ASSESSMENT")
    print("-" * 70)

    print(report["assessment"])

    print("\nRECOMMENDATION")
    print("-" * 70)

    print(report["recommendation"])


if __name__ == "__main__":
    print_daily_report()