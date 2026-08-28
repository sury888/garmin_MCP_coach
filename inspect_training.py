from datetime import date
from pprint import pprint

from garmin_client import GarminClient


def main():
    garmin = GarminClient()
    garmin.login()

    today = date.today().isoformat()

    training_status = garmin.client.get_training_status(today)

    print("=" * 60)
    print("TRAINING STATUS STRUCTURE")
    print("=" * 60)

    pprint(training_status, sort_dicts=False)


if __name__ == "__main__":
    main()