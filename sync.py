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


def sync_day(garmin, day, sync_activities=True):
    """
    Sync one day's health data and, optionally, activities.

    Returns a structured result dict instead of only printing, so
    callers can tell exactly what succeeded/failed for this day rather
    than inferring it from stdout. `sync_activities=False` skips the
    (expensive, paginated) full-history activity pull below, for
    callers that already sync activities separately -- this also
    avoids redundantly re-pulling the whole activity list once per day
    in a multi-day loop.
    """

    day_string = day.isoformat()

    print(f"\nSyncing {day_string}...")

    result = {
        "date": day_string,
        "health_saved": False,
        "health_error": None,
        "activities_saved": 0,
        "activities_error": None,
    }

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

        result["health_saved"] = True
        print("  ✓ Daily health")

    except Exception as e:
        result["health_error"] = f"{type(e).__name__}: {e}"
        print(f"  ✗ Daily health: {e}")

    # =========================================================
    # ACTIVITIES
    # =========================================================

    if sync_activities:
        try:
            activities = garmin.get_all_activities(max_activities=1000)
            saved = 0
            for raw in activities:
                parsed = parse_activity(raw)
                if parsed.get("activity_date") == day:
                    save_activity(parsed)
                    saved += 1
            result["activities_saved"] = saved
            print(f"  ✓ Activities ({saved})")
        except Exception as e:
            result["activities_error"] = f"{type(e).__name__}: {e}"
            print(f"  ✗ Activities: {e}")

    return result


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


def sync_garmin_history(days=7):
    """
    Backfill both activities and daily health over an arbitrary number
    of days (not limited to 7).

    Reuses the existing, already-working sync_activity_history() for
    the activities side (chunked date-range pulls, handles arbitrary
    history lengths), and sync_day(..., sync_activities=False) for the
    health side, so health backfill never redundantly re-pulls the
    full activity list once per day. Activities and health are synced
    independently: a failure in one is recorded but does not prevent
    or invalidate the other.
    """
    initialize_database()

    errors = []

    # ACTIVITIES -- reuse the existing chunked backfill implementation.
    activity_result = sync_activity_history(days=days)
    errors.extend(activity_result.get("errors", []))

    # HEALTH -- independent of the activities sync above.
    today = date.today()
    start_date = today - timedelta(days=max(0, days - 1))

    garmin = None
    health_days_attempted = 0
    health_days_saved = 0

    try:
        garmin = GarminClient()
        garmin.login()
    except Exception as e:
        errors.append({
            "stage": "health_login",
            "error": f"{type(e).__name__}: {e}",
        })

    if garmin is not None:
        import time

        for days_ago in range(days):
            day = today - timedelta(days=days_ago)
            health_days_attempted += 1

            day_result = sync_day(garmin, day, sync_activities=False)

            if day_result.get("health_saved"):
                health_days_saved += 1
            else:
                errors.append({
                    "stage": "health",
                    "date": day_result.get("date", day.isoformat()),
                    "error": day_result.get("health_error"),
                })

            time.sleep(2)

    return {
        "success": len(errors) == 0,
        "start_date": start_date.isoformat(),
        "end_date": today.isoformat(),
        "days_requested": days,
        "activities_seen": activity_result.get("activities_seen", 0),
        "activities_saved": activity_result.get("activities_saved", 0),
        "health_days_attempted": health_days_attempted,
        "health_days_saved": health_days_saved,
        "errors": errors,
    }


def sync_latest_garmin_data():
    """
    Sync recent Garmin data needed for coaching decisions.

    Activities and health are synced independently of each other, and
    each health day is attempted independently of the other -- a
    failure in any one stage is captured in `errors` rather than
    aborting the whole call. The sync is only marked complete (see
    freshness.mark_sync_complete, which gates is_data_fresh()) when
    both health days this tool promises -- today and yesterday -- were
    actually saved. A partial result is reported as partial, never
    silently treated as current.
    """

    initialize_database()

    errors = []
    synced_at = datetime.now().isoformat()

    # ---------------------------------------------------------
    # LOGIN
    # ---------------------------------------------------------

    garmin = None

    try:
        garmin = GarminClient()
        garmin.login()
    except Exception as e:
        errors.append({
            "stage": "login",
            "error": f"{type(e).__name__}: {e}",
        })

    # ---------------------------------------------------------
    # ACTIVITIES -- independent of health below.
    # ---------------------------------------------------------

    activities_synced = 0

    if garmin is not None:
        try:
            activities = garmin.get_activities(limit=20)

            for activity in activities:
                try:
                    parsed = parse_activity(activity)
                    save_activity(parsed)
                    activities_synced += 1

                except Exception as e:
                    errors.append({
                        "stage": "activity",
                        "activity_id": activity.get("activityId") if isinstance(activity, dict) else None,
                        "error": f"{type(e).__name__}: {e}",
                    })

        except Exception as e:
            errors.append({
                "stage": "activities_fetch",
                "error": f"{type(e).__name__}: {e}",
            })

    # ---------------------------------------------------------
    # HEALTH -- today and yesterday, each attempted independently.
    # Garmin metrics can sometimes finalize after the calendar day
    # changes, which is why both days are re-attempted on every call.
    # sync_activities=False here because activities were already
    # synced above; re-pulling the full activity history once per day
    # was redundant and is the likely cause of this tool's previous
    # intermittent failures under Garmin API load.
    # ---------------------------------------------------------

    today = date.today()
    health_days_saved = 0
    health_results = []

    if garmin is not None:
        for days_ago in range(2):
            day = today - timedelta(days=days_ago)

            try:
                day_result = sync_day(garmin, day, sync_activities=False)
            except Exception as e:
                # sync_day() already catches its own errors; this guards
                # against anything unexpected escaping it, so one bad day
                # can never take the other day down with it.
                day_result = {
                    "date": day.isoformat(),
                    "health_saved": False,
                    "health_error": f"{type(e).__name__}: {e}",
                }

            health_results.append(day_result)

            if day_result.get("health_saved"):
                health_days_saved += 1
            else:
                errors.append({
                    "stage": "health",
                    "date": day_result.get("date", day.isoformat()),
                    "error": day_result.get("health_error"),
                })

    # ---------------------------------------------------------
    # MARK SUCCESSFUL SYNC -- only when both promised health days
    # actually saved. Never mark the database current on a partial
    # or failed sync.
    # ---------------------------------------------------------

    sync_marked_complete = False

    if garmin is not None and health_days_saved == 2:
        from freshness import mark_sync_complete

        mark_sync_complete()
        sync_marked_complete = True

    return {
        "success": len(errors) == 0,
        "synced_at": synced_at,
        "activities_synced": activities_synced,
        "health_days_synced": health_days_saved,
        "health_results": health_results,
        "sync_marked_complete": sync_marked_complete,
        "errors": errors,
    }

if __name__ == "__main__":
    sync_history(30)