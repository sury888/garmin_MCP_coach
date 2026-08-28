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