from datetime import datetime, timedelta

from database import (
    get_sync_state,
    set_sync_state,
)


SYNC_TTL_MINUTES = 10


def is_data_fresh():
    """
    Check whether Garmin data was synced recently enough
    for coaching decisions.
    """

    last_sync = get_sync_state("last_garmin_sync")

    if not last_sync:
        return False

    try:
        last_sync_time = datetime.fromisoformat(last_sync)
    except ValueError:
        return False

    age = datetime.now() - last_sync_time

    return age < timedelta(minutes=SYNC_TTL_MINUTES)


def mark_sync_complete():
    set_sync_state(
        "last_garmin_sync",
        datetime.now().isoformat(),
    )


def get_last_sync():
    return get_sync_state("last_garmin_sync")