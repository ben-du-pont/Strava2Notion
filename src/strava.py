"""
Strava API integration module for fetching triathlon activities.
"""

import os
import requests
from typing import Dict, List, Optional


class StravaClient:
    """Client for interacting with the Strava API."""

    BASE_URL = "https://www.strava.com/api/v3"
    # Activity types as returned by Strava API
    # "Ride" is the official Strava type for cycling activities
    # "VirtualRide" is used for indoor/virtual cycling (e.g. Zwift)
    TRIATHLON_ACTIVITY_TYPES = ["Swim", "Ride", "VirtualRide", "Run"]

    # Mapping from Strava sport types to Notion sport types
    SPORT_TYPE_MAPPING = {
        "Ride": "Bike",        # Strava uses "Ride", Notion uses "Bike"
        "VirtualRide": "Bike", # Virtual rides map to the same Bike category in Notion
        "Run": "Run",
        "Swim": "Swim"
    }
    
    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None, 
                 refresh_token: Optional[str] = None):
        """
        Initialize the Strava client.
        
        Args:
            client_id: Strava client ID (defaults to STRAVA_CLIENT_ID env var)
            client_secret: Strava client secret (defaults to STRAVA_CLIENT_SECRET env var)
            refresh_token: Strava refresh token (defaults to STRAVA_REFRESH_TOKEN env var)
        """
        self.client_id = client_id or os.getenv("STRAVA_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("STRAVA_CLIENT_SECRET")
        self.refresh_token = refresh_token or os.getenv("STRAVA_REFRESH_TOKEN")
        self.access_token = None
        
    def get_access_token(self) -> str:
        """
        Get a valid access token using the refresh token.

        Returns:
            Access token string

        Note:
            This method handles sensitive credentials. Never log the response or tokens.
        """
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise ValueError("Missing Strava credentials")

        url = "https://www.strava.com/oauth/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token"
        }

        response = requests.post(url, data=payload)
        response.raise_for_status()

        data = response.json()
        self.access_token = data["access_token"]
        # Never log the access token
        return self.access_token
    
    def get_activities(self, after: Optional[int] = None, before: Optional[int] = None, 
                      per_page: int = 30) -> List[Dict]:
        """
        Fetch activities from Strava.
        
        Args:
            after: Unix timestamp to filter activities after this date
            before: Unix timestamp to filter activities before this date
            per_page: Number of activities to fetch per page
            
        Returns:
            List of activity dictionaries
        """
        if not self.access_token:
            self.get_access_token()
            
        url = f"{self.BASE_URL}/athlete/activities"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"per_page": per_page}
        
        if after:
            params["after"] = after
        if before:
            params["before"] = before
            
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def get_activity_details(self, activity_id: int) -> Dict:
        """
        Fetch detailed information about a specific activity.
        
        Args:
            activity_id: The ID of the activity
            
        Returns:
            Activity detail dictionary
        """
        if not self.access_token:
            self.get_access_token()
            
        url = f"{self.BASE_URL}/activities/{activity_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        return response.json()
    
    def filter_triathlon_activities(self, activities: List[Dict],
                                   activity_types: Optional[List[str]] = None) -> List[Dict]:
        """
        Filter activities to include only triathlon-related activities.

        Args:
            activities: List of activity dictionaries
            activity_types: List of activity types to include (defaults to TRIATHLON_ACTIVITY_TYPES)

        Returns:
            Filtered list of triathlon activities (swim, bike, run)
        """
        if activity_types is None:
            activity_types = self.TRIATHLON_ACTIVITY_TYPES

        return [
            activity for activity in activities
            if activity.get("type") in activity_types or activity.get("sport_type") in activity_types
        ]

    def get_notion_sport_type(self, strava_sport_type: str) -> str:
        """
        Convert Strava sport type to Notion sport type.

        Args:
            strava_sport_type: Sport type from Strava (e.g., "Ride", "Run", "Swim")

        Returns:
            Notion-compatible sport type (e.g., "Bike", "Run", "Swim")
        """
        return self.SPORT_TYPE_MAPPING.get(strava_sport_type, strava_sport_type)
