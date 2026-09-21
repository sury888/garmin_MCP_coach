import os

from dotenv import load_dotenv
from garminconnect import Garmin


class GarminClient:
    def __init__(self):
        load_dotenv()

        email = os.getenv("GARMIN_EMAIL")
        password = os.getenv("GARMIN_PASSWORD")

        if not email or not password:
            raise ValueError(
                "GARMIN_EMAIL and GARMIN_PASSWORD must be set in .env"
            )

        self.client = Garmin(email, password)

    def login(self):
        """Authenticate with Garmin Connect."""
        self.client.login()

    def get_activities(self, limit=10):
        """Return the most recent Garmin activities."""
        return self.client.get_activities(0, limit)

    def get_activities_by_date(self, startdate, enddate=None, activitytype=None, sortorder=None):
        """Return Garmin activities in a date range using Garmin's date-range endpoint."""
        return self.client.get_activities_by_date(
            startdate, enddate, activitytype, sortorder
        )

    def get_activity(self, activity_id):
        """Return Garmin's activity summary payload when available."""
        return self.client.get_activity(activity_id)

    def get_activity_details(self, activity_id):
        """Return detailed activity data."""
        return self.client.get_activity_details(activity_id)

    def get_activity_splits(self, activity_id):
        """Return Garmin-native lap/split data."""
        return self.client.get_activity_splits(activity_id)

    def get_activity_hr_zones(self, activity_id):
        """Return heart-rate zone data."""
        return self.client.get_activity_hr_zones(activity_id)

    def get_activity_data(self, activity_id):
        """
        Return both Garmin-native laps and detailed activity samples.
        """
        details = self.get_activity_details(activity_id)
        splits = self.get_activity_splits(activity_id)

        return {
            "details": details,
            "splits": splits,
            "laps": splits.get("lapDTOs", []),
        }

    def get_all_activities(self, max_activities=1000):
        """
        Download Garmin activities using pagination.
        """

        all_activities = []

        page = 0
        page_size = 100

        while len(all_activities) < max_activities:

            print(
                f"Downloading activities "
                f"{page * page_size + 1}-"
                f"{(page + 1) * page_size}..."
            )

            activities = self.client.get_activities(
                page * page_size,
                page_size
            )

            if not activities:
                break

            all_activities.extend(activities)

            print(
                f"  Retrieved {len(activities)}"
            )

            if len(activities) < page_size:
                break

            page += 1

        return all_activities[:max_activities]