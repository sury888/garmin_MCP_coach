from workout_relationships import analyze_workout_recovery


def main():

    results = analyze_workout_recovery(14)

    print("=" * 70)
    print("WORKOUT → RECOVERY ANALYSIS")
    print("=" * 70)

    for day in results:

        print(f"\n{day['date']}")

        print(
            f"  Activities: "
            f"{day['activities']}"
        )

        print(
            f"  Training load: "
            f"{day['training_load']:.1f}"
        )

        print(
            f"  Duration: "
            f"{day['duration_hours']:.2f} hrs"
        )

        print(
            f"  HRV: "
            f"{day['hrv']}"
        )

        if day["next_day_hrv_change"] is not None:

            print(
                f"  Next-day HRV change: "
                f"{day['next_day_hrv_change']:+.1f}%"
            )

        print(
            f"  Readiness: "
            f"{day['readiness']}"
        )


if __name__ == "__main__":
    main()