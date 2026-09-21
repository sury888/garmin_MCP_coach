from coach import generate_coaching_analysis


print("TEST COACH STARTING")


def main():

    print("Running coaching analysis...")

    analysis = generate_coaching_analysis()

    print("Analysis returned.")

    print("=" * 70)
    print("GARMIN COACH — TREND ANALYSIS")
    print("=" * 70)

    if not analysis:
        print("Not enough data.")
        return

    print(f"\nDate: {analysis['date']}")

    print("\nMULTI-DAY TRENDS")
    print("-" * 70)

    for metric, trend in analysis["trends"]["trends"].items():

        print(f"\n{metric}")

        print(
            f"  Overall change: "
            f"{trend['overall_change_percent']:+.1f}%"
        )

        if "consecutive_down" in trend:
            print(
                f"  Consecutive down: "
                f"{trend['consecutive_down']}"
            )

        if "consecutive_up" in trend:
            print(
                f"  Consecutive up: "
                f"{trend['consecutive_up']}"
            )

    print("\nCOACHING SIGNALS")
    print("-" * 70)

    if not analysis["signals"]:
        print("No multi-day warning patterns detected.")

    else:
        for signal in analysis["signals"]:
            print(f"⚠ {signal}")


if __name__ == "__main__":
    main()