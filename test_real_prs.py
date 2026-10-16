
from datetime import date
from sqlalchemy import func

from database import SessionLocal, Activity
from performance_queries import (
    get_best_performance,
    get_best_swim_performance,
)


def summarize(label, result):
    print(f"\n--- {label} ---")

    if not isinstance(result, dict):
        print("Unexpected result type:", type(result).__name__)
        return

    # Keep the output focused on the actual result and data quality.
    keys = (
        "sport", "target", "target_units", "window_days", "period",
        "period_start", "period_end", "found", "reason",
        "activity_name", "date", "surface", "pace_source",
        "duration_seconds", "best_power_w", "time_seconds",
        "pace_per_mile", "pace_per_100m", "pace_per_100yd",
        "pool_length", "pool_length_unit", "stroke",
        "activities_considered", "activities_in_course",
        "activities_excluded", "errors",
    )
    for key in keys:
        if key in result:
            print(f"{key}: {result[key]}")

    if isinstance(result.get("results"), list):
        for row in result["results"]:
            print("PR:", row)


def run_query(label, fn):
    try:
        summarize(label, fn())
    except Exception as exc:
        print(f"\n--- {label}: ERROR ---")
        print(f"{type(exc).__name__}: {exc}")


# 1. Check what activity history is already in the local database.
with SessionLocal() as session:
    count = session.query(func.count(Activity.activity_id)).scalar()
    first_date = session.query(func.min(Activity.activity_date)).scalar()
    last_date = session.query(func.max(Activity.activity_date)).scalar()

    print("=== LOCAL GARMIN DATABASE ===")
    print("Activity count:", count)
    print("Earliest activity:", first_date)
    print("Latest activity:", last_date)
    print("Today's date:", date.today())

# 2. Test exact rolling efforts against the most recent 30 days.
# Bike target is duration in seconds; run target is distance in meters.
run_query(
    "Bike: best 5-minute power, last 30 days",
    lambda: get_best_performance(
        "bike", 300, metric="duration", window_days=30
    ),
)

run_query(
    "Run: fastest 5K, last 30 days",
    lambda: get_best_performance(
        "run", 5000, metric="distance", window_days=30
    ),
)

# 3. Test yard and meter swim PRs independently.
run_query(
    "Swim: 100-yard PR, last 30 days",
    lambda: get_best_swim_performance(
        unit="yards", target=100, window_days=30
    ),
)

run_query(
    "Swim: 100-meter PR, last 30 days",
    lambda: get_best_swim_performance(
        unit="meters", target=100, window_days=30
    ),
)

print("\n=== TEST FINISHED ===")
