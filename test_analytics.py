from analytics import (
    get_health_history,
    get_activity_history,
    calculate_training_summary,
)


def main():

    # =========================================================
    # HEALTH
    # =========================================================

    health = get_health_history(3)

    print("\nHEALTH HISTORY")
    print("=" * 70)

    for day in health:

        print(
            f"{day.date} | "
            f"RHR {day.resting_hr} | "
            f"HRV {day.hrv} | "
            f"Sleep {day.sleep_hours:.1f}h | "
            f"Readiness {day.training_readiness} | "
            f"Load {day.acute_load}"
        )

    # =========================================================
    # ACTIVITIES
    # =========================================================

    activities = get_activity_history(3)

    print("\nACTIVITY HISTORY")
    print("=" * 70)

    for activity in activities:

        duration_minutes = (
            (activity.duration_seconds or 0) / 60
        )

        print(
            f"{activity.activity_date} | "
            f"{activity.activity_name} | "
            f"{duration_minutes:.1f} min | "
            f"Load {activity.training_load}"
        )

    # =========================================================
    # TRAINING SUMMARY
    # =========================================================

    summary = calculate_training_summary(3)

    print("\nTRAINING SUMMARY")
    print("=" * 70)

    print(
        f"Activities: "
        f"{summary['activities']}"
    )

    print(
        f"Total duration: "
        f"{summary['total_duration_seconds'] / 3600:.2f} hours"
    )

    print(
        f"Total distance: "
        f"{summary['total_distance_meters'] / 1000:.2f} km"
    )

    print(
        f"Total training load: "
        f"{summary['total_training_load']:.1f}"
    )

    print("\nBY SPORT")

    for sport, data in summary["sport_summary"].items():

        print(
            f"{sport}: "
            f"{data['activities']} activities | "
            f"{data['duration'] / 3600:.2f} hrs | "
            f"{data['distance'] / 1000:.2f} km | "
            f"load {data['training_load']:.1f}"
        )


if __name__ == "__main__":
    main()