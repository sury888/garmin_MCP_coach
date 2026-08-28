from garmin_client import GarminClient


def main():
    print("Connecting to Garmin...")

    garmin = GarminClient()
    garmin.login()

    print("Connected!\n")

    activities = garmin.get_activities(10)

    print(f"Retrieved {len(activities)} activities:\n")

    for activity in activities:
        name = activity.get("activityName")
        date = activity.get("startTimeLocal")
        distance = activity.get("distance", 0)
        duration = activity.get("duration", 0)

        print(
            f"{date} | "
            f"{name} | "
            f"{distance / 1000:.2f} km | "
            f"{duration / 60:.1f} min"
        )


if __name__ == "__main__":
    main()