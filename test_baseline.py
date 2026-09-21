














from baseline import calculate_baselines


def main():

    baselines = calculate_baselines(30)

    print("=" * 70)
    print("PERSONAL BASELINES — 30 DAYS")
    print("=" * 70)

    if not baselines:
        print("No health data available.")
        return

    for metric, data in baselines.items():

        print(f"\n{metric}")

        print(
            f"  Days:   {data['count']}"
        )

        print(
            f"  Mean:   {data['mean']:.2f}"
        )

        print(
            f"  Median: {data['median']:.2f}"
        )

        print(
            f"  Min:    {data['min']:.2f}"
        )

        print(
            f"  Max:    {data['max']:.2f}"
        )

        if data["std_dev"] is not None:

            print(
                f"  StdDev: {data['std_dev']:.2f}"
            )


if __name__ == "__main__":
    main()