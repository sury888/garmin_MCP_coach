from analytics import get_health_history


def _percent_change(old, new):
    if old is None or new is None or old == 0:
        return None

    return ((new - old) / old) * 100


def _average(values):
    values = [v for v in values if v is not None]

    if not values:
        return None

    return sum(values) / len(values)


def get_health_trends(days: int = 30) -> dict:
    """
    Analyze health and recovery trends over the requested period.

    Compares the first half of the period with the second half
    and identifies meaningful changes.
    """

    history = get_health_history(days)

    if len(history) < 4:
        return {
            "error": "Not enough health history for trend analysis."
        }

    # Database returns oldest -> newest
    midpoint = len(history) // 2

    first_half = history[:midpoint]
    second_half = history[midpoint:]

    metrics = [
        "resting_hr",
        "hrv",
        "sleep_hours",
        "sleep_score",
        "body_battery",
        "stress",
        "acute_load",
        "chronic_load",
        "acwr",
    ]

    trends = {}

    for metric in metrics:

        first_values = [
            getattr(day, metric, None)
            for day in first_half
        ]

        second_values = [
            getattr(day, metric, None)
            for day in second_half
        ]

        first_avg = _average(first_values)
        second_avg = _average(second_values)

        if first_avg is None or second_avg is None:
            continue

        change = _percent_change(
            first_avg,
            second_avg
        )

        if change is None:
            continue

        if abs(change) < 3:
            direction = "stable"
        elif change > 0:
            direction = "increasing"
        else:
            direction = "decreasing"

        trends[metric] = {
            "first_half_average": round(first_avg, 2),
            "second_half_average": round(second_avg, 2),
            "change_percent": round(change, 2),
            "direction": direction,
        }

    # ---------------------------------------------------------
    # Identify coaching signals
    # ---------------------------------------------------------

    signals = []

    hrv = trends.get("hrv")

    if hrv and hrv["change_percent"] <= -10:
        signals.append(
            "HRV has declined significantly over the period."
        )

    rhr = trends.get("resting_hr")

    if rhr and rhr["change_percent"] >= 5:
        signals.append(
            "Resting HR has increased significantly."
        )

    sleep = trends.get("sleep_hours")

    if sleep and sleep["change_percent"] <= -5:
        signals.append(
            "Average sleep duration has decreased."
        )

    body_battery = trends.get("body_battery")

    if body_battery and body_battery["change_percent"] <= -10:
        signals.append(
            "Average Body Battery has declined."
        )

    acute_load = trends.get("acute_load")

    if acute_load and acute_load["change_percent"] >= 15:
        signals.append(
            "Acute training load has increased significantly."
        )

    acwr = trends.get("acwr")

    if acwr and acwr["second_half_average"] >= 1.2:
        signals.append(
            "Average ACWR is elevated."
        )

    # ---------------------------------------------------------
    # Overall interpretation
    # ---------------------------------------------------------

    negative_signals = 0

    if hrv and hrv["change_percent"] <= -10:
        negative_signals += 1

    if rhr and rhr["change_percent"] >= 5:
        negative_signals += 1

    if sleep and sleep["change_percent"] <= -5:
        negative_signals += 1

    if body_battery and body_battery["change_percent"] <= -10:
        negative_signals += 1

    if negative_signals >= 3:
        overall = "declining_recovery"
    elif negative_signals == 2:
        overall = "mixed_recovery"
    else:
        overall = "stable"

    return {
        "days_analyzed": len(history),
        "first_half_days": len(first_half),
        "second_half_days": len(second_half),

        "trends": trends,

        "coaching_signals": signals,

        "overall_recovery_trend": overall,
    }