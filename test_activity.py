from datetime import date

from garmin_client import GarminClient
from activity_parser import parse_activity
from database import initialize_database, save_activity


def main():

    initialize_database()

    today = date.today().isoformat()

    garmin = GarminClient()
    garmin.login()

    print("Getting recent Garmin activities...")

    activities = garmin.client.get_activities(
        0,
        5
    )

    print(f"Found {len(activities)} activities.")

    for activity in activities:

        parsed = parse_activity(activity)

        save_activity(parsed)

        print("\n" + "=" * 50)

        print(f"ID: {parsed['activity_id']}")
        print(f"Date: {parsed['activity_date']}")
        print(f"Name: {parsed['activity_name']}")
        print(f"Type: {parsed['activity_type']}")
        print(f"Duration: {parsed['duration_seconds']}")
        print(f"Distance: {parsed['distance_meters']}")
        print(f"Avg HR: {parsed['avg_heart_rate']}")
        print(f"Max HR: {parsed['max_heart_rate']}")
        print(f"Avg Power: {parsed['avg_power']}")
        print(f"Calories: {parsed['calories']}")

    print("\nActivities saved successfully.")


if __name__ == "__main__":
    main()