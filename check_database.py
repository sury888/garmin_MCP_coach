from database import get_session, DailyHealth, Activity


def main():

    session = get_session()

    # =========================================================
    # DAILY HEALTH
    # =========================================================

    health_records = (
        session.query(DailyHealth)
        .order_by(DailyHealth.date.desc())
        .all()
    )

    print("\nDAILY HEALTH")
    print("=" * 70)

    if not health_records:
        print("No daily health records yet.")

    for record in health_records:

        print(f"\nDate: {record.date}")
        print(f"Resting HR: {record.resting_hr}")
        print(f"HRV: {record.hrv}")
        print(f"Sleep: {record.sleep_hours:.2f} hours" if record.sleep_hours else "Sleep: None")
        print(f"Sleep Score: {record.sleep_score}")
        print(f"Body Battery: {record.body_battery}")
        print(f"Stress: {record.stress}")
        print(f"Readiness: {record.training_readiness}")
        print(f"Acute Load: {record.acute_load}")
        print(f"Chronic Load: {record.chronic_load}")
        print(f"ACWR: {record.acwr}")
        print(f"Training Status: {record.training_status}")
        print(f"Training Feedback: {record.training_status_feedback}")

    # =========================================================
    # ACTIVITIES
    # =========================================================

    activities = (
        session.query(Activity)
        .order_by(
            Activity.activity_date.desc(),
            Activity.activity_id.desc()
        )
        .all()
    )

    print("\n\nACTIVITIES")
    print("=" * 70)

    if not activities:
        print("No activities yet.")

    for activity in activities:

        print(f"\nDate: {activity.activity_date}")
        print(f"Name: {activity.activity_name}")
        print(f"Type: {activity.activity_type}")
        print(f"Duration: {activity.duration_seconds:.1f}s")
        print(f"Distance: {activity.distance_meters}")
        print(f"Avg HR: {activity.avg_heart_rate}")
        print(f"Max HR: {activity.max_heart_rate}")
        print(f"Avg Power: {activity.avg_power}")
        print(f"Normalized Power: {activity.normalized_power}")
        print(f"Avg Cadence: {activity.avg_cadence}")
        print(f"Elevation Gain: {activity.elevation_gain}")
        print(f"Training Effect: {activity.training_effect}")
        print(f"Training Load: {activity.training_load}")
        print(f"Swolf: {activity.avg_swolf}")
        print(f"Strokes: {activity.total_strokes}")
        print(f"VO2 Max: {activity.vo2max}")

    session.close()


if __name__ == "__main__":
    main()