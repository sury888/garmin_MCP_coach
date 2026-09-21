from datetime import datetime
import json


def parse_activity(activity):
    """
    Convert Garmin's activity response into our database format.
    """

    activity_id = activity.get("activityId")

    # =========================================================
    # DATE
    # =========================================================

    start_time = activity.get("startTimeLocal")

    activity_date = None

    if start_time:
        try:
            activity_date = datetime.fromisoformat(
                start_time
            ).date()
        except ValueError:
            pass

    # =========================================================
    # ACTIVITY TYPE
    # =========================================================

    activity_type = None

    activity_type_data = activity.get(
        "activityType",
        {}
    )

    if isinstance(activity_type_data, dict):
        activity_type = activity_type_data.get(
            "typeKey"
        )

    # =========================================================
    # ACTIVITY DATA
    # =========================================================

    return {

        # -----------------------------------------------------
        # GENERAL
        # -----------------------------------------------------

        "activity_id": activity_id,

        "activity_date": activity_date,

        "activity_name": activity.get(
            "activityName"
        ),

        "activity_type": activity_type,

        "duration_seconds": activity.get(
            "duration"
        ),

        "distance_meters": activity.get(
            "distance"
        ),

        "calories": activity.get(
            "calories"
        ),

        # -----------------------------------------------------
        # HEART RATE
        # -----------------------------------------------------

        "avg_heart_rate": activity.get(
            "averageHR"
        ),

        "max_heart_rate": activity.get(
            "maxHR"
        ),

        # -----------------------------------------------------
        # SPEED
        # -----------------------------------------------------

        "avg_speed": activity.get(
            "averageSpeed"
        ),

        "max_speed": activity.get(
            "maxSpeed"
        ),

        # -----------------------------------------------------
        # CYCLING POWER
        # -----------------------------------------------------

        "avg_power": activity.get(
            "averagePower"
        ),

        "normalized_power": activity.get(
            "normPower"
        ),

        "max_power": activity.get(
            "maxPower"
        ),

        # -----------------------------------------------------
        # CADENCE
        # -----------------------------------------------------

        "avg_cadence": activity.get(
            "averageBikingCadenceInRevPerMinute"
        ),

        "max_cadence": activity.get(
            "maxBikingCadenceInRevPerMinute"
        ),

        # -----------------------------------------------------
        # ELEVATION
        # -----------------------------------------------------

        "elevation_gain": activity.get(
            "elevationGain"
        ),

        "elevation_loss": activity.get(
            "elevationLoss"
        ),

        # -----------------------------------------------------
        # RUNNING DYNAMICS
        # -----------------------------------------------------

        "avg_running_cadence": activity.get(
            "averageRunningCadenceInStepsPerMinute"
        ),

        "max_running_cadence": activity.get(
            "maxRunningCadenceInStepsPerMinute"
        ),

        "avg_stride_length": activity.get(
            "avgStrideLength"
        ),

        "vertical_oscillation": activity.get(
            "avgVerticalOscillation"
        ),

        "vertical_ratio": activity.get(
            "avgVerticalRatio"
        ),

        "ground_contact_time": activity.get(
            "avgGroundContactTime"
        ),

        # -----------------------------------------------------
        # TRAINING EFFECT / LOAD
        # -----------------------------------------------------

        "training_effect": activity.get(
            "aerobicTrainingEffect"
        ),

        "anaerobic_training_effect": activity.get(
            "anaerobicTrainingEffect"
        ),

        "training_load": activity.get(
            "activityTrainingLoad"
        ),

        # -----------------------------------------------------
        # SWIMMING
        # -----------------------------------------------------

        "pool_length": activity.get(
            "poolLength"
        ),

        "total_strokes": activity.get(
            "strokes"
        ),

        "avg_swolf": activity.get(
            "averageSwolf"
        ),

        "avg_stroke_rate": activity.get(
            "averageStrokeRate"
        ),

        # -----------------------------------------------------
        # VO2 MAX
        # -----------------------------------------------------

        "vo2max": activity.get(
            "vO2MaxValue"
        ),

        # -----------------------------------------------------
        # RAW DATA
        # -----------------------------------------------------

        "raw_data": json.dumps(
            activity,
            default=str
        ),
    }