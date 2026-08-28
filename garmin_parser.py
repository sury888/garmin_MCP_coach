from datetime import date


def parse_daily_health(
    stats,
    hrv,
    sleep,
    body_battery,
    stress,
    respiration,
    training_readiness,
    training_status,
):
    """
    Convert Garmin's raw responses into our clean DailyHealth format.
    """

    today = date.today()

    # ---------------------------------------------------------
    # RESTING HEART RATE
    # ---------------------------------------------------------

    resting_hr = stats.get("restingHeartRate")

    # ---------------------------------------------------------
    # HRV
    # ---------------------------------------------------------

    hrv_value = None

    if hrv:
        summary = hrv.get("hrvSummary", {})

        hrv_value = (
            summary.get("weeklyAvg")
            or summary.get("lastNightAvg")
        )

    # ---------------------------------------------------------
    # SLEEP
    # ---------------------------------------------------------

    sleep_hours = None
    sleep_score = None

    if sleep:
        sleep_dto = sleep.get("dailySleepDTO", {})

        duration_seconds = sleep_dto.get("sleepTimeSeconds")

        if duration_seconds:
            sleep_hours = duration_seconds / 3600

        sleep_score_data = sleep_dto.get("sleepScores", {})

        if isinstance(sleep_score_data, dict):
            overall = sleep_score_data.get("overall")

            if isinstance(overall, dict):
                sleep_score = overall.get("value")

    # ---------------------------------------------------------
    # BODY BATTERY
    # ---------------------------------------------------------

    body_battery_value = None

    if body_battery:
        if isinstance(body_battery, list):
            values = []

            for item in body_battery:
                value = item.get("charged", 0)

                if value:
                    values.append(value)

            if values:
                body_battery_value = max(values)

    # ---------------------------------------------------------
    # STRESS
    # ---------------------------------------------------------

    stress_value = None

    if isinstance(stress, dict):
        stress_value = stress.get("overallStressLevel")

    # ---------------------------------------------------------
    # RESPIRATION
    # ---------------------------------------------------------

    respiration_avg = None
    respiration_min = None
    respiration_max = None

    if isinstance(respiration, dict):

        respiration_avg = respiration.get(
            "avgWakingRespirationValue"
        )

        respiration_min = respiration.get(
            "lowestRespirationValue"
        )

        respiration_max = respiration.get(
            "highestRespirationValue"
        )

    # ---------------------------------------------------------
    # TRAINING READINESS
    # ---------------------------------------------------------

    readiness_score = None
    readiness_level = None
    acute_load = None

    if training_readiness:

        # Garmin may return multiple readiness records.
        latest = training_readiness[0]

        readiness_score = latest.get("score")
        readiness_level = latest.get("level")

        acute_load = latest.get("acuteLoad")

    # ---------------------------------------------------------
    # TRAINING STATUS
    # ---------------------------------------------------------

    chronic_load = None
    acwr = None
    training_status_value = None

    if training_status:

        status_data = training_status.get(
            "latestTrainingStatusData",
            {}
        )

        if status_data:

            # Garmin keys this by device ID
            device_data = next(
                iter(status_data.values())
            )

            training_status_value = (
                device_data.get(
                    "trainingStatusFeedbackPhrase"
                )
            )

            load_data = device_data.get(
                "acuteTrainingLoadDTO",
                {}
            )

            chronic_load = load_data.get(
                "dailyTrainingLoadChronic"
            )

            acwr = load_data.get(
                "dailyAcuteChronicWorkloadRatio"
            )

            # Prefer the load from training status
            if load_data.get("dailyTrainingLoadAcute") is not None:
                acute_load = load_data.get(
                    "dailyTrainingLoadAcute"
                )

    # ---------------------------------------------------------
    # RETURN CLEAN RECORD
    # ---------------------------------------------------------

    return {
        "date": today,

        "resting_hr": resting_hr,
        "hrv": hrv_value,

        "respiration_avg": respiration_avg,
        "respiration_min": respiration_min,
        "respiration_max": respiration_max,

        "sleep_hours": sleep_hours,
        "sleep_score": sleep_score,

        "body_battery": body_battery_value,
        "stress": stress_value,

        "training_readiness": readiness_score,
        "training_readiness_level": readiness_level,

        "acute_load": acute_load,
        "chronic_load": chronic_load,
        "acwr": acwr,

        "training_status": training_status_value,
    }