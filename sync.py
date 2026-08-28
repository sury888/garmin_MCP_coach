from datetime import date

from garmin_client import GarminClient
from garmin_parser import parse_daily_health
from database import initialize_database, save_daily_health


def sync_today():

    today = date.today().isoformat()

    print(f"Syncing Garmin data for {today}...")

    # ---------------------------------------------------------
    # CONNECT
    # ---------------------------------------------------------

    garmin = GarminClient()
    garmin.login()

    print("Connected to Garmin.")

    # ---------------------------------------------------------
    # GET DATA
    # ---------------------------------------------------------

    stats = garmin.client.get_stats(today)

    hrv = garmin.client.get_hrv_data(today)

    sleep = garmin.client.get_sleep_data(today)

    body_battery = garmin.client.get_body_battery(today)

    stress = garmin.client.get_stress_data(today)

    respiration = garmin.client.get_respiration_data(today)

    training_readiness = (
        garmin.client.get_training_readiness(today)
    )

    training_status = (
        garmin.client.get_training_status(today)
    )

    # ---------------------------------------------------------
    # PARSE
    # ---------------------------------------------------------

    daily_health = parse_daily_health(
        stats=stats,
        hrv=hrv,
        sleep=sleep,
        body_battery=body_battery,
        stress=stress,
        respiration=respiration,
        training_readiness=training_readiness,
        training_status=training_status,
    )

    # ---------------------------------------------------------
    # SAVE
    # ---------------------------------------------------------

    save_daily_health(daily_health)

    print("\nSuccessfully saved today's data.")

    print("\nDaily Health")
    print("=" * 50)

    for key, value in daily_health.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    initialize_database()
    sync_today()