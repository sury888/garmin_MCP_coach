from database import get_session, DailyHealth


def main():

    session = get_session()

    records = session.query(DailyHealth).all()

    print("\nDATABASE CONTENTS")
    print("=" * 50)

    for record in records:

        print(f"\nDate: {record.date}")
        print(f"Resting HR: {record.resting_hr}")
        print(f"HRV: {record.hrv}")
        print(f"Sleep: {record.sleep_hours}")
        print(f"Sleep Score: {record.sleep_score}")
        print(f"Body Battery: {record.body_battery}")
        print(f"Stress: {record.stress}")
        print(f"Readiness: {record.training_readiness}")
        print(f"Acute Load: {record.acute_load}")
        print(f"Chronic Load: {record.chronic_load}")
        print(f"ACWR: {record.acwr}")
        print(f"Training Status: {record.training_status}")

    session.close()


if __name__ == "__main__":
    main()