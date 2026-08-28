from datetime import date
import json

from garmin_client import GarminClient


def main():
    garmin = GarminClient()
    garmin.login()

    today = date.today().isoformat()

    data = {}

    print("Connecting to Garmin...")
    print("Collecting data...\n")

    # ---------------------------------------------------------
    # ACTIVITIES
    # ---------------------------------------------------------

    try:
        data["activities"] = garmin.client.get_activities(0, 5)
        print("✅ Activities")
    except Exception as e:
        print(f"❌ Activities: {e}")

    # ---------------------------------------------------------
    # DAILY STATS
    # ---------------------------------------------------------

    try:
        data["daily_stats"] = garmin.client.get_stats(today)
        print("✅ Daily stats")
    except Exception as e:
        print(f"❌ Daily stats: {e}")

    # ---------------------------------------------------------
    # TRAINING READINESS
    # ---------------------------------------------------------

    try:
        data["training_readiness"] = garmin.client.get_training_readiness(today)
        print("✅ Training readiness")
    except Exception as e:
        print(f"❌ Training readiness: {e}")

    # ---------------------------------------------------------
    # HRV
    # ---------------------------------------------------------

    try:
        data["hrv"] = garmin.client.get_hrv_data(today)
        print("✅ HRV")
    except Exception as e:
        print(f"❌ HRV: {e}")

    # ---------------------------------------------------------
    # SLEEP
    # ---------------------------------------------------------

    try:
        data["sleep"] = garmin.client.get_sleep_data(today)
        print("✅ Sleep")
    except Exception as e:
        print(f"❌ Sleep: {e}")

    # ---------------------------------------------------------
    # BODY BATTERY
    # ---------------------------------------------------------

    try:
        data["body_battery"] = garmin.client.get_body_battery(today)
        print("✅ Body Battery")
    except Exception as e:
        print(f"❌ Body Battery: {e}")

    # ---------------------------------------------------------
    # STRESS
    # ---------------------------------------------------------

    try:
        data["stress"] = garmin.client.get_stress_data(today)
        print("✅ Stress")
    except Exception as e:
        print(f"❌ Stress: {e}")

    # ---------------------------------------------------------
    # RESPIRATION
    # ---------------------------------------------------------

    try:
        data["respiration"] = garmin.client.get_respiration_data(today)
        print("✅ Respiration")
    except Exception as e:
        print(f"❌ Respiration: {e}")

    # ---------------------------------------------------------
    # TRAINING STATUS
    # ---------------------------------------------------------

    try:
        data["training_status"] = garmin.client.get_training_status(today)
        print("✅ Training status")
    except Exception as e:
        print(f"❌ Training status: {e}")

    # ---------------------------------------------------------
    # SAVE EVERYTHING
    # ---------------------------------------------------------

    with open("garmin_test_data.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, default=str)

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"Saved data to: garmin_test_data.json")


if __name__ == "__main__":
    main()