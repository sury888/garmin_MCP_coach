from garminconnect import Garmin


EMAIL = "suryzeboss8@gmail.com"
PASSWORD = "Sury#boss8"


def main():
    print("Connecting to Garmin...")

    client = Garmin(EMAIL, PASSWORD)
    client.login()

    print("Successfully connected!")

    activities = client.get_activities(0, 5)

    print(f"\nFound {len(activities)} activities:\n")

    for activity in activities:
        print(
            f"{activity.get('startTimeLocal')} | "
            f"{activity.get('activityName')} | "
            f"{activity.get('activityType', {}).get('typeKey')} | "
            f"{activity.get('distance', 0):.2f} m | "
            f"{activity.get('duration', 0):.0f} sec"
        )


if __name__ == "__main__":
    main()