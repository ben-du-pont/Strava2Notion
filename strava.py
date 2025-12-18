"""
Strava API integration module.

Handles authentication and fetching activities from Strava.
"""

import os
import logging
from typing import Dict, List, Optional
import requests


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class StravaClient:
    """Client for interacting with the Strava API."""

    BASE_URL = "https://www.strava.com/api/v3"
    TOKEN_URL = "https://www.strava.com/oauth/token"

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        """
        Initialize the Strava client.

        Args:
            client_id: Strava application client ID
            client_secret: Strava application client secret
            refresh_token: Strava refresh token for authentication
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token: Optional[str] = None

    def get_access_token(self) -> str:
        """
        Get a fresh access token using the refresh token.

        Returns:
            str: Valid access token

        Raises:
            Exception: If token refresh fails
        """
        try:
            payload = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token
            }

            response = requests.post(self.TOKEN_URL, data=payload)
            response.raise_for_status()

            token_data = response.json()
            self.access_token = token_data['access_token']
            logger.info("Successfully refreshed Strava access token")
            return self.access_token

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to refresh Strava access token: {e}")
            raise

    def get_activities(
            self,
            after: Optional[int] = None,
            per_page: int = 30) -> List[Dict]:
        """
        Fetch athlete activities from Strava.

        Args:
            after: Epoch timestamp to fetch activities after (optional)
            per_page: Number of activities per page (default: 30)

        Returns:
            List of activity dictionaries

        Raises:
            Exception: If API request fails
        """
        if not self.access_token:
            self.get_access_token()

        try:
            headers = {'Authorization': f'Bearer {self.access_token}'}
            params = {'per_page': per_page}

            if after:
                params['after'] = after

            response = requests.get(
                f"{self.BASE_URL}/athlete/activities",
                headers=headers,
                params=params
            )
            response.raise_for_status()

            activities = response.json()
            logger.info(f"Successfully fetched {len(activities)} activities from Strava")
            return activities

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch Strava activities: {e}")
            raise


def get_strava_client() -> StravaClient:
    """
    Create a Strava client from environment variables.

    Returns:
        StravaClient: Configured Strava client

    Raises:
        ValueError: If required environment variables are missing
    """
    client_id = os.getenv('STRAVA_CLIENT_ID')
    client_secret = os.getenv('STRAVA_CLIENT_SECRET')
    refresh_token = os.getenv('STRAVA_REFRESH_TOKEN')

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError(
            "Missing required Strava environment variables: "
            "STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN"
        )

    return StravaClient(client_id, client_secret, refresh_token)
