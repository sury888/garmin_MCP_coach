import json

from database import get_session, Activity


def main():
    session = get_session()

    activities = (
        session.query(Activity)
        .order_by(Activity.activity_date.desc())
        .limit(5)
        .all()
    )

    print("=" * 70)
    print("GARMIN ACTIVITY FIELD AUDIT")
    print("=" * 70)

    for activity in activities:

        print("\n" + "=" * 70)
        print(f"{activity.activity_name}")
        print(f"Type: {activity.activity_type}")
        print(f"Date: {activity.activity_date}")
        print(f"ID: {activity.activity_id}")
        print("=" * 70)

        raw = json.loads(activity.raw_data)

        for key, value in raw.items():
            print(f"{key}: {value}")

    session.close()


if __name__ == "__main__":
    main()