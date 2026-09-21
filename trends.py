from datetime import date, timedelta
from statistics import mean

from analytics import get_health_history
from baseline import calculate_baselines


def calculate_deviation(value, baseline):

    if value is None or baseline is None:
        return None

    if baseline == 0:
        return None

    return ((value - baseline) / baseline) * 100


def calculate_z_score(value, mean_value, std_dev):

    if value is None or std_dev is None:
        return None

    if std_dev == 0:
        return 0

    return (value - mean_value) / std_dev


def analyze_metric(
    value,
    baseline,
    metric_name,
    higher_is_worse=False,
):
    """
    Analyze today's value relative to the user's
    personal baseline.
    """

    if value is None or metric_name not in baseline:
        return None

    baseline_data = baseline[metric_name]

    mean_value = baseline_data["mean"]
    std_dev = baseline_data["std_dev"]

    deviation = calculate_deviation(
        value,
        mean_value
    )

    z_score = calculate_z_score(
        value,
        mean_value,
        std_dev
    )

    # Determine direction
    if deviation is None:
        direction = "unknown"

    elif deviation > 0:
        direction = "above"

    elif deviation < 0:
        direction = "below"

    else:
        direction = "normal"

    # Generic flag
    flag = "normal"

    if z_score is not None:

        if higher_is_worse:

            if z_score >= 2:
                flag = "high"

            elif z_score >= 1:
                flag = "elevated"

            elif z_score <= -1:
                flag = "low"

        else:

            if z_score <= -2:
                flag = "very_low"

            elif z_score <= -1:
                flag = "low"

            elif z_score >= 1:
                flag = "high"

    return {
        "metric": metric_name,
        "value": value,
        "baseline": mean_value,
        "deviation_percent": deviation,
        "z_score": z_score,
        "direction": direction,
        "flag": flag,
    }


def analyze_today():

    health = get_health_history(30)

    if not health:
        return None

    # Most recent record
    today = health[-1]

    baselines = calculate_baselines(30)

    results = {}

    results["resting_hr"] = analyze_metric(
        today.resting_hr,
        baselines,
        "resting_hr",
        higher_is_worse=True,
    )

    results["hrv"] = analyze_metric(
        today.hrv,
        baselines,
        "hrv",
        higher_is_worse=False,
    )

    results["sleep_hours"] = analyze_metric(
        today.sleep_hours,
        baselines,
        "sleep_hours",
        higher_is_worse=False,
    )

    results["sleep_score"] = analyze_metric(
        today.sleep_score,
        baselines,
        "sleep_score",
        higher_is_worse=False,
    )

    results["body_battery"] = analyze_metric(
        today.body_battery,
        baselines,
        "body_battery",
        higher_is_worse=False,
    )

    results["stress"] = analyze_metric(
        today.stress,
        baselines,
        "stress",
        higher_is_worse=True,
    )

    results["training_readiness"] = analyze_metric(
        today.training_readiness,
        baselines,
        "training_readiness",
        higher_is_worse=False,
    )

    results["acute_load"] = analyze_metric(
        today.acute_load,
        baselines,
        "acute_load",
        higher_is_worse=True,
    )

    results["acwr"] = analyze_metric(
        today.acwr,
        baselines,
        "acwr",
        higher_is_worse=True,
    )

    return {
        "date": today.date,
        "results": results,
    }