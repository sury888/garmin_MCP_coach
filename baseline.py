from statistics import mean, median, stdev

from analytics import get_health_history


def calculate_baselines(days=30):

    records = get_health_history(days)

    if not records:
        return None

    def values(attribute):
        return [
            getattr(record, attribute)
            for record in records
            if getattr(record, attribute) is not None
        ]

    metrics = {
        "resting_hr": values("resting_hr"),
        "hrv": values("hrv"),
        "sleep_hours": values("sleep_hours"),
        "sleep_score": values("sleep_score"),
        "body_battery": values("body_battery"),
        "stress": values("stress"),
        "training_readiness": values(
            "training_readiness"
        ),
        "acute_load": values("acute_load"),
        "chronic_load": values("chronic_load"),
        "acwr": values("acwr"),
    }

    baselines = {}

    for name, data in metrics.items():

        if not data:
            continue

        result = {
            "count": len(data),
            "mean": mean(data),
            "median": median(data),
            "min": min(data),
            "max": max(data),
        }

        if len(data) >= 2:
            result["std_dev"] = stdev(data)
        else:
            result["std_dev"] = None

        baselines[name] = result

    return baselines