from datetime import date, timedelta, datetime

from garmin_client import GarminClient
from garmin_parser import parse_daily_health
from activity_parser import parse_activity
from database import (
    initialize_database,
    save_daily_health,
    save_activity,
)


_garmin = None


def get_garmin():
    global _garmin

    if _garmin is None:
        _garmin = GarminClient()
        _garmin.login()

    return _garmin


def sync_day(garmin, day):
    """
    Sync one day's health data and activities.
    """

    day_string = day.isoformat()

    print(f"\nSyncing {day_string}...")

    # =========================================================
    # DAILY HEALTH
    # =========================================================

    try:
        stats = garmin.client.get_stats(day_string)
        hrv = garmin.client.get_hrv_data(day_string)
        sleep = garmin.client.get_sleep_data(day_string)
        body_battery = garmin.client.get_body_battery(day_string)
        stress = garmin.client.get_stress_data(day_string)
        respiration = garmin.client.get_respiration_data(day_string)

        training_readiness = (
            garmin.client.get_training_readiness(day_string)
        )

        training_status = (
            garmin.client.get_training_status(day_string)
        )

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

        # IMPORTANT:
        # The parser currently uses today's date.
        # We need to override it with the date being synced.
        daily_health["date"] = day

        save_daily_health(daily_health)

        print("  ✓ Daily health")

    except Exception as e:
        print(f"  ✗ Daily health: {e}")

    # =========================================================
    # ACTIVITIES
    # =========================================================

    try:
        activities = garmin.get_all_activities(max_activities=1000)
        saved = 0
        for raw in activities:
            parsed = parse_activity(raw)
            if parsed.get("activity_date") == day:
                save_activity(parsed)
                saved += 1
        print(f"  ✓ Activities ({saved})")
    except Exception as e:
        print(f"  ✗ Activities: {e}")


def sync_history(days=30):

    initialize_database()

    print("=" * 70)
    print(f"GARMIN HISTORICAL SYNC — {days} DAYS")
    print("=" * 70)

    garmin = GarminClient()
    garmin.login()

    today = date.today()

    start_date = today - timedelta(days=days - 1)

    # =========================================================
    # GET ACTIVITIES ONCE
    # =========================================================

    print("\nDownloading recent activities...")

    activities = garmin.get_all_activities(
        max_activities=1000
    )

    print(
        f"Downloaded {len(activities)} activities."
    )

    # Group activities by date
    activities_by_date = {}

    for activity in activities:

        parsed = parse_activity(activity)

        activity_date = parsed["activity_date"]

        if activity_date is None:
            continue

        if start_date <= activity_date <= today:

            activities_by_date.setdefault(
                activity_date,
                []
            ).append(parsed)

    # Save activities
    for activity_list in activities_by_date.values():

        for activity in activity_list:
            save_activity(activity)

    print(
        f"Saved {sum(len(x) for x in activities_by_date.values())} "
        "activities."
    )

    # =========================================================
    # DAILY HEALTH
    # =========================================================

    for days_ago in range(days):

        day = today - timedelta(days=days_ago)

        sync_day(
            garmin,
            day
        )

        import time
        time.sleep(2)

    print("\n" + "=" * 70)
    print("HISTORICAL SYNC COMPLETE")
    print("=" * 70)

def sync_activity_history(days=3650, chunk_days=30):
    """
    Sync activity summaries across an arbitrarily long history.

    Uses Garmin's date-range activity endpoint in bounded chunks instead of
    requesting a giant activity list. This is intended for full-history
    backfills and can safely overlap existing database rows.
    """
    initialize_database()

    garmin = GarminClient()
    garmin.login()

    today = date.today()
    start_date = today - timedelta(days=max(0, days - 1))
    chunk_days = max(1, int(chunk_days))

    chunks = []
    cursor = start_date

    while cursor <= today:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), today)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)

    total_seen = 0
    total_saved = 0
    errors = []

    for chunk_start, chunk_end in chunks:
        try:
            raw_activities = garmin.get_activities_by_date(
                chunk_start.isoformat(),
                chunk_end.isoformat(),
            )

            saved = 0
            for raw in raw_activities or []:
                try:
                    parsed = parse_activity(raw)
                    if parsed.get("activity_date") is not None:
                        save_activity(parsed)
                        saved += 1
                except Exception as e:
                    errors.append({
                        "activity_id": raw.get("activityId") if isinstance(raw, dict) else None,
                        "error": f"{type(e).__name__}: {e}",
                    })

            total_seen += len(raw_activities or [])
            total_saved += saved

        except Exception as e:
            errors.append({
                "chunk_start": chunk_start.isoformat(),
                "chunk_end": chunk_end.isoformat(),
                "error": f"{type(e).__name__}: {e}",
            })

    return {
        "success": len(errors) == 0,
        "start_date": start_date.isoformat(),
        "end_date": today.isoformat(),
        "chunk_days": chunk_days,
        "chunks": len(chunks),
        "activities_seen": total_seen,
        "activities_saved": total_saved,
        "errors": errors,
    }


def sync_latest_garmin_data():
    """
    Sync recent Garmin data needed for coaching decisions.
    """

    initialize_database()

    garmin = GarminClient()
    garmin.login()

    today = date.today()

    # ---------------------------------------------------------
    # ACTIVITIES
    # ---------------------------------------------------------

    activities = garmin.get_activities(limit=20)

    for activity in activities:

        try:
            parsed = parse_activity(activity)
            save_activity(parsed)

        except Exception as e:
            print(f"Activity sync error: {e}")

    # ---------------------------------------------------------
    # HEALTH
    # ---------------------------------------------------------

    # Sync today and yesterday because Garmin metrics can
    # sometimes finalize after the calendar day changes.

    for days_ago in range(2):

        day = today - timedelta(days=days_ago)

        sync_day(
            garmin,
            day,
        )

    # ---------------------------------------------------------
    # MARK SUCCESSFUL SYNC
    # ---------------------------------------------------------

    from freshness import mark_sync_complete

    mark_sync_complete()

    return {
        "success": True,
        "synced_at": datetime.now().isoformat(),
        "activities_synced": len(activities),
        "health_days_synced": 2,
    }

if __name__ == "__main__":
    sync_history(30)