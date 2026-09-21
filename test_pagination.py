from garmin_client import GarminClient


def main():

    garmin = GarminClient()
    garmin.login()

    activities = garmin.get_all_activities(
        max_activities=250
    )

    print("\n" + "=" * 70)
    print("PAGINATION TEST")
    print("=" * 70)

    print(
        f"Total activities retrieved: "
        f"{len(activities)}"
    )

    if activities:

        print(
            f"Newest: "
            f"{activities[0].get('activityName')}"
        )

        print(
            f"Oldest: "
            f"{activities[-1].get('activityName')}"
        )


if __name__ == "__main__":
    main()