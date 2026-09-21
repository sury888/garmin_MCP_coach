"""Robust parser for Garmin activity detail streams.

Garmin has returned activityDetailMetrics rows as both dictionaries
({'metrics': [...]}) and bare metric lists. Normalize both forms here so the
performance engine can operate on bike/run/swim streams consistently.
"""
from datetime import datetime, timezone
from typing import Any


def _descriptor_map(data: dict[str, Any]) -> dict[int, str]:
    descriptors = {}
    raw = data.get("metricDescriptors", [])
    if isinstance(raw, dict):
        raw = raw.values()

    for item in raw or []:
        if not isinstance(item, dict):
            continue
        idx = item.get("metricsIndex")
        key = item.get("key")
        if idx is None or not key:
            continue
        try:
            descriptors[int(idx)] = str(key)
        except (TypeError, ValueError):
            continue
    return descriptors


def parse_activity_details(data):
    if not isinstance(data, dict):
        return []

    descriptors = _descriptor_map(data)
    rows = data.get("activityDetailMetrics", [])
    if not isinstance(rows, list):
        return []

    samples = []

    for row in rows:
        # Garmin normally returns {'metrics': [...]}, but some activity
        # responses expose the metric array directly.
        if isinstance(row, dict):
            metrics = row.get("metrics", [])
        elif isinstance(row, (list, tuple)):
            metrics = row
        else:
            continue

        if not isinstance(metrics, (list, tuple)):
            continue

        sample = {}
        for index, value in enumerate(metrics):
            key = descriptors.get(index)
            if key and value is not None:
                sample[key] = value

        if "directTimestamp" in sample:
            try:
                sample["timestamp"] = datetime.fromtimestamp(
                    float(sample["directTimestamp"]) / 1000,
                    tz=timezone.utc,
                ).isoformat()
            except (TypeError, ValueError, OverflowError, OSError):
                pass

        samples.append(sample)

    return samples
