import os
import threading
from pathlib import Path

from dotenv import load_dotenv


class GarminClient:
    """
    Shared Garmin Connect client for the lifetime of the MCP process.

    The Garmin SDK is imported lazily so importing the MCP server does not
    initialize the Garmin HTTP stack during MCP startup. The underlying
    Garmin client/session is created once and authentication is idempotent.
    Persisted Garmin tokens are reused between MCP restarts when available.
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        load_dotenv()

        email = os.getenv("GARMIN_EMAIL")
        password = os.getenv("GARMIN_PASSWORD")

        if not email or not password:
            raise ValueError(
                "GARMIN_EMAIL and GARMIN_PASSWORD must be set in .env"
            )

        tokenstore = os.getenv("GARMINTOKENS")
        if not tokenstore:
            local_app_data = os.getenv("LOCALAPPDATA")
            if local_app_data:
                tokenstore = str(
                    Path(local_app_data)
                    / "garminCustomMcp"
                    / "garmin_tokens"
                )
            else:
                tokenstore = str(
                    Path.home()
                    / ".garminCustomMcp"
                    / "garmin_tokens"
                )

        self.tokenstore = tokenstore

        # Lazy import: do not load garminconnect during MCP module import.
        from garminconnect import Garmin

        # One Garmin object = one reusable HTTP session for this MCP process.
        self.client = Garmin(email, password)
        self._login_lock = threading.Lock()
        self._authenticated = False
        self._initialized = True

    def login(self):
        """Authenticate with Garmin Connect at most once per MCP process."""
        if self._authenticated:
            return

        with self._login_lock:
            if self._authenticated:
                return

            self.client.login(tokenstore=self.tokenstore)
            self._authenticated = True

    def get_activities(self, limit=10):
        self.login()
        return self.client.get_activities(0, limit)

    def get_activities_by_date(
        self, startdate, enddate=None, activitytype=None, sortorder=None
    ):
        self.login()
        return self.client.get_activities_by_date(
            startdate, enddate, activitytype, sortorder
        )

    def get_activity(self, activity_id):
        self.login()
        return self.client.get_activity(activity_id)

    def get_activity_details(self, activity_id):
        self.login()
        return self.client.get_activity_details(activity_id)

    def get_activity_splits(self, activity_id):
        self.login()
        return self.client.get_activity_splits(activity_id)

    def get_activity_hr_zones(self, activity_id):
        self.login()
        return self.client.get_activity_hr_zones(activity_id)

    def get_activity_data(self, activity_id):
        self.login()
        details = self.get_activity_details(activity_id)
        splits = self.get_activity_splits(activity_id)
        return {
            "details": details,
            "splits": splits,
            "laps": splits.get("lapDTOs", []),
        }

    def get_all_activities(self, max_activities=1000):
        self.login()
        all_activities = []
        page = 0
        page_size = 100

        while len(all_activities) < max_activities:
            activities = self.client.get_activities(
                page * page_size, page_size
            )
            if not activities:
                break

            all_activities.extend(activities)
            if len(activities) < page_size:
                break
            page += 1

        return all_activities[:max_activities]


# Explicit helper for tools that want to document/use the shared client.
def get_garmin_client() -> GarminClient:
    client = GarminClient()
    client.login()
    return client
