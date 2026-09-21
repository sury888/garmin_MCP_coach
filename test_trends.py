from trends import analyze_today


def main():

    analysis = analyze_today()

    print("=" * 70)
    print("TODAY VS PERSONAL BASELINE")
    print("=" * 70)

    if not analysis:
        print("No data available.")
        return

    print(f"\nDate: {analysis['date']}")

    for metric, result in analysis["results"].items():

        if result is None:
            continue

        print(f"\n{metric}")

        print(
            f"  Today:     {result['value']:.2f}"
        )

        print(
            f"  Baseline:  {result['baseline']:.2f}"
        )

        print(
            f"  Deviation: "
            f"{result['deviation_percent']:+.1f}%"
        )

        if result["z_score"] is not None:

            print(
                f"  Z-score:   "
                f"{result['z_score']:+.2f}"
            )

        print(
            f"  Flag:      "
            f"{result['flag']}"
        )


if __name__ == "__main__":
    main()