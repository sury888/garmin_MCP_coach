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

    # =========================================================
    # RESTING HEART RATE
    # =========================================================

    resting_hr = stats.get("restingHeartRate")

    # =========================================================
    # HRV
    # =========================================================

    hrv_value = None

    if hrv:
        summary = hrv.get("hrvSummary", {})

        if summary:
            hrv_value = (
                summary.get("weeklyAvg")
                or summary.get("lastNightAvg")
                or summary.get("weeklyAverage")
            )

    # =========================================================
    # SLEEP
    # =========================================================

    sleep_hours = None
    sleep_score = None

    if sleep:
        sleep_dto = sleep.get("dailySleepDTO", {})

        if sleep_dto:
            duration_seconds = sleep_dto.get("sleepTimeSeconds")

            if duration_seconds:
                sleep_hours = duration_seconds / 3600

            sleep_scores = sleep_dto.get(
                "sleepScores",
                {}
            )

            if isinstance(sleep_scores, dict):
                overall = sleep_scores.get("overall")

                if isinstance(overall, dict):
                    sleep_score = overall.get("value")

    # =========================================================
    # BODY BATTERY
    # =========================================================

    body_battery_value = None

    if body_battery:

        if isinstance(body_battery, list):

            values = []

            for item in body_battery:

                if not isinstance(item, dict):
                    continue

                charged = item.get("charged")

                if charged is not None:
                    values.append(charged)

            if values:
                body_battery_value = max(values)

        elif isinstance(body_battery, dict):

            # Try common Garmin fields
            body_battery_value = (
                body_battery.get("bodyBatteryMostRecentValue")
                or body_battery.get("bodyBatteryValue")
            )

    # =========================================================
    # STRESS
    # =========================================================

    stress_value = None

    if isinstance(stress, dict):

        # Garmin can expose this under different fields.
        stress_value = (
            stress.get("overallStressLevel")
            or stress.get("avgStressLevel")
            or stress.get("averageStressLevel")
        )

    # =========================================================
    # RESPIRATION
    # =========================================================

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

    # =========================================================
    # TRAINING READINESS
    # =========================================================

    readiness_score = None
    readiness_level = None
    acute_load = None

    if training_readiness:

        # Garmin returns multiple readiness snapshots.
        # The first entry is the most recent one in our response.
        latest = training_readiness[0]

        readiness_score = latest.get("score")
        readiness_level = latest.get("level")

        acute_load = latest.get("acuteLoad")

    # =========================================================
    # TRAINING STATUS / LOAD
    # =========================================================

    chronic_load = None
    acwr = None
    training_status_value = None
    training_status_feedback = None


    if training_status:

        # -----------------------------------------------------
        # Garmin structure:
        #
        # latestTrainingStatusData
        #     └── device ID
        #           └── training data
        # -----------------------------------------------------

        most_recent = training_status.get(
            "mostRecentTrainingStatus",
            {}
        )

        status_container = most_recent.get(
            "latestTrainingStatusData",
            {}
        )

        if status_container:

            # Get the device-specific training status.
            device_data = next(
                iter(status_container.values()),
                None
            )

            if device_data:

                # Garmin's numeric training status
                # Example: 4
                training_status_value = device_data.get(
                    "trainingStatus"
                )

                training_status_feedback = device_data.get(
                    "trainingStatusFeedbackPhrase"
                )
                load_data = device_data.get(
                    "acuteTrainingLoadDTO",
                    {}
                )

                if load_data:

                    acute_load = (
                        load_data.get(
                            "dailyTrainingLoadAcute"
                        )
                        or acute_load
                    )

                    chronic_load = load_data.get(
                        "dailyTrainingLoadChronic"
                    )

                    acwr = load_data.get(
                        "dailyAcuteChronicWorkloadRatio"
                    )

    # =========================================================
    # RETURN CLEAN RECORD
    # =========================================================

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
        "training_status_feedback": training_status_feedback,
    }