from datetime import date

from sqlalchemy import create_engine, Column, Integer, Float, String, Date, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = "sqlite:///garmin_coach.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"timeout": 10, "check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()
class SyncState(Base):
    __tablename__ = "sync_state"

    key = Column(String, primary_key=True)
    value = Column(String)

from datetime import date, timedelta

from garmin_client import GarminClient
from garmin_parser import parse_daily_health
from activity_parser import parse_activity
# from database import (
#     initialize_database,
#     save_daily_health,
#     save_activity,
# )


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


if __name__ == "__main__":
    sync_history(30)


class DailyHealth(Base):
    __tablename__ = "daily_health"

    date = Column(Date, primary_key=True)

    resting_hr = Column(Integer)
    hrv = Column(Float)

    respiration_avg = Column(Float)
    respiration_min = Column(Float)
    respiration_max = Column(Float)

    sleep_hours = Column(Float)
    sleep_score = Column(Float)

    body_battery = Column(Integer)
    stress = Column(Float)

    training_readiness = Column(Float)
    training_readiness_level = Column(String)

    acute_load = Column(Float)
    chronic_load = Column(Float)
    acwr = Column(Float)

    training_status = Column(Integer)
    training_status_feedback = Column(String)


def initialize_database():
    Base.metadata.create_all(engine)
    # Lightweight SQLite migration for existing installs.
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    with engine.begin() as conn:
        if "performance_records" in tables:
            existing = {c["name"] for c in inspector.get_columns("performance_records")}
            for name, sql_type in (("window_start", "TEXT"), ("window_end", "TEXT"), ("metric_json", "TEXT")):
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE performance_records ADD COLUMN {name} {sql_type}"))

        # SQLite create_all() does not add columns to an already-existing
        # table. These fields were added to ActivityAnnotation after some
        # users had already created the database, so migrate them explicitly.
        if "activity_annotations" in tables:
            existing = {c["name"] for c in inspector.get_columns("activity_annotations")}
            for name, sql_type in (
                ("swim_subtype", "TEXT"),
                ("swim_set_description", "TEXT"),
                ("swim_lap_indices", "TEXT"),
                ("manual_treadmill_intervals", "TEXT"),
            ):
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE activity_annotations ADD COLUMN {name} {sql_type}"))


def get_session():
    session = SessionLocal()
    # SQLite is used by the local MCP server; keep transactions short and
    # avoid leaving a connection in an implicit transaction.
    return session


def save_daily_health(data):
    session = get_session()

    try:
        existing = session.query(DailyHealth).filter_by(
            date=data["date"]
        ).first()

        if existing:
            for key, value in data.items():
                if key != "date":
                    setattr(existing, key, value)

        else:
            health = DailyHealth(**data)
            session.add(health)

        session.commit()

    finally:
        session.close()


class Activity(Base):
    __tablename__ = "activities"

    activity_id = Column(Integer, primary_key=True)

    # =========================================================
    # GENERAL
    # =========================================================

    activity_date = Column(Date)
    activity_name = Column(String)
    activity_type = Column(String)

    duration_seconds = Column(Float)
    distance_meters = Column(Float)

    calories = Column(Float)

    # =========================================================
    # HEART RATE
    # =========================================================

    avg_heart_rate = Column(Integer)
    max_heart_rate = Column(Integer)

    # =========================================================
    # SPEED / PACE
    # =========================================================

    avg_speed = Column(Float)
    max_speed = Column(Float)

    # =========================================================
    # CYCLING
    # =========================================================

    avg_power = Column(Float)
    normalized_power = Column(Float)

    max_power = Column(Float)

    avg_cadence = Column(Float)
    max_cadence = Column(Float)

    elevation_gain = Column(Float)
    elevation_loss = Column(Float)

    # =========================================================
    # RUNNING
    # =========================================================

    avg_running_cadence = Column(Float)
    max_running_cadence = Column(Float)

    avg_stride_length = Column(Float)

    vertical_oscillation = Column(Float)
    vertical_ratio = Column(Float)

    ground_contact_time = Column(Float)

    # =========================================================
    # TRAINING EFFECT / LOAD
    # =========================================================

    training_effect = Column(Float)
    anaerobic_training_effect = Column(Float)

    training_load = Column(Float)

    # =========================================================
    # SWIMMING
    # =========================================================

    pool_length = Column(Float)

    total_strokes = Column(Integer)

    avg_swolf = Column(Float)

    avg_stroke_rate = Column(Float)

    # =========================================================
    # OTHER
    # =========================================================

    vo2max = Column(Float)

    # =========================================================
    # RAW GARMIN RESPONSE
    # =========================================================

    raw_data = Column(String)


class ActivityAnnotation(Base):
    __tablename__ = "activity_annotations"

    activity_id = Column(Integer, primary_key=True)
    note = Column(String)
    bike_position = Column(String)
    interval_positions = Column(String)
    swim_subtype = Column(String)
    swim_set_description = Column(String)
    swim_lap_indices = Column(String)
    manual_treadmill_intervals = Column(String)
    source = Column(String, default="user")
    updated_at = Column(String)


class PerformanceRecord(Base):
    """Cached peak-performance result for one Garmin activity."""

    __tablename__ = "performance_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(Integer, nullable=False, index=True)
    sport = Column(String, nullable=False, index=True)
    metric_type = Column(String, nullable=False)

    duration_seconds = Column(Float)
    distance_m = Column(Float)

    # Primary metric: watts for bike; seconds/km for run; seconds/100m for swim.
    primary_value = Column(Float)

    avg_hr = Column(Float)
    max_hr = Column(Float)
    cadence = Column(Float)

    watts_per_kg = Column(Float)
    kilojoules = Column(Float)
    power_hr_ratio = Column(Float)

    # Advanced performance analytics
    window_start = Column(String)
    window_end = Column(String)
    metric_json = Column(String)


class WeatherObservation(Base):
    __tablename__ = "weather_observations"

    activity_id = Column(Integer, primary_key=True)
    observed_at = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    temperature_c = Column(Float)
    relative_humidity = Column(Float)
    apparent_temperature_c = Column(Float)
    precipitation_mm = Column(Float)
    wind_speed_kmh = Column(Float)
    wind_direction_deg = Column(Float)
    shortwave_radiation_wm2 = Column(Float)
    uv_index = Column(Float)


class AthleteProfile(Base):
    __tablename__ = "athlete_profile"

    id = Column(Integer, primary_key=True)
    ftp = Column(Float)
    run_threshold_pace_sec_per_km = Column(Float)
    css_sec_per_100m = Column(Float)
    weight_kg = Column(Float)


class DailyTrainingLoad(Base):
    __tablename__ = "daily_training_load"

    date = Column(Date, primary_key=True)
    garmin_load = Column(Float, default=0)
    tss = Column(Float)
    tss_activities = Column(Integer, default=0)
    bike_tss = Column(Float)
    run_tss = Column(Float)
    swim_tss = Column(Float)
    strength_load = Column(Float, default=0)
    duration_seconds = Column(Float, default=0)
    bike_duration_seconds = Column(Float, default=0)
    run_duration_seconds = Column(Float, default=0)
    swim_duration_seconds = Column(Float, default=0)
    atl = Column(Float)
    ctl = Column(Float)
    tsb = Column(Float)
    # Threshold-derived TrainingPeaks-style load balance, kept separate from
    # Garmin-native load balance.
    tss_atl = Column(Float)
    tss_ctl = Column(Float)
    tss_tsb = Column(Float)


class PlannedWorkout(Base):
    __tablename__ = "planned_workouts"

    id = Column(Integer, primary_key=True, autoincrement=True)

    workout_date = Column(Date, nullable=False)

    sport = Column(String, nullable=False)

    workout_name = Column(String, nullable=False)

    duration_minutes = Column(Integer)

    intensity = Column(String)

    description = Column(String)

    completed = Column(Integer, default=0)


def save_activity(data):
    session = get_session()

    try:
        existing = session.query(Activity).filter_by(
            activity_id=data["activity_id"]
        ).first()

        if existing:
            for key, value in data.items():
                if key != "activity_id":
                    setattr(existing, key, value)

        else:
            activity = Activity(**data)
            session.add(activity)

        session.commit()

    finally:
        session.close()


def save_planned_workout(data):
    session = get_session()

    try:
        workout = PlannedWorkout(**data)
        session.add(workout)
        session.commit()
        session.refresh(workout)

        return workout

    finally:
        session.close()


def get_planned_workout(workout_date):
    session = get_session()

    try:
        return (
            session.query(PlannedWorkout)
            .filter_by(workout_date=workout_date)
            .order_by(PlannedWorkout.id.desc())
            .first()
        )

    finally:
        session.close()


def get_sync_state(key):
    session = get_session()

    try:
        state = session.query(SyncState).filter_by(key=key).first()
        return state.value if state else None
    finally:
        session.close()


def set_sync_state(key, value):
    session = get_session()

    try:
        existing = session.query(SyncState).filter_by(key=key).first()

        if existing:
            existing.value = value
        else:
            session.add(
                SyncState(
                    key=key,
                    value=value,
                )
            )

        session.commit()

    finally:
        session.close()