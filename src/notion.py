"""
Notion API integration module for managing triathlon training database.
"""

import os
import requests
from typing import Dict, List, Optional


class NotionClient:
    """Client for interacting with the Notion API."""
    
    BASE_URL = "https://api.notion.com/v1"
    NOTION_VERSION = "2022-06-28"
    
    def __init__(self, token: Optional[str] = None, database_id: Optional[str] = None):
        """
        Initialize the Notion client.
        
        Args:
            token: Notion integration token (defaults to NOTION_TOKEN env var)
            database_id: Notion database ID (defaults to NOTION_DATABASE_ID env var)
        """
        self.token = token or os.getenv("NOTION_TOKEN")
        self.database_id = database_id or os.getenv("NOTION_DATABASE_ID")
        
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for Notion API requests."""
        if not self.token:
            raise ValueError("Missing Notion token")
            
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.NOTION_VERSION,
            "Content-Type": "application/json"
        }
    
    def query_database(self, filter_params: Optional[Dict] = None) -> List[Dict]:
        """
        Query the Notion database.
        
        Args:
            filter_params: Optional filter parameters for the query
            
        Returns:
            List of page objects from the database
        """
        if not self.database_id:
            raise ValueError("Missing Notion database ID")
            
        url = f"{self.BASE_URL}/databases/{self.database_id}/query"
        headers = self._get_headers()
        
        payload = {}
        if filter_params:
            payload["filter"] = filter_params
            
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        return response.json().get("results", [])
    
    def create_page(self, properties: Dict) -> Dict:
        """
        Create a new page in the Notion database.
        
        Args:
            properties: Dictionary of page properties
            
        Returns:
            Created page object
        """
        if not self.database_id:
            raise ValueError("Missing Notion database ID")
            
        url = f"{self.BASE_URL}/pages"
        headers = self._get_headers()
        
        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties
        }
        
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    def update_page(self, page_id: str, properties: Dict) -> Dict:
        """
        Update an existing page in the Notion database.
        
        Args:
            page_id: The ID of the page to update
            properties: Dictionary of page properties to update
            
        Returns:
            Updated page object
        """
        url = f"{self.BASE_URL}/pages/{page_id}"
        headers = self._get_headers()
        
        payload = {"properties": properties}
        
        response = requests.patch(url, headers=headers, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    def activity_to_properties(self, activity: Dict) -> Dict:
        """
        Convert a Strava activity to Notion page properties.
        
        Args:
            activity: Strava activity dictionary
            
        Returns:
            Dictionary of Notion properties
        """
        properties = {
            "Name": {
                "title": [
                    {
                        "text": {
                            "content": activity.get("name", "Untitled Activity")
                        }
                    }
                ]
            },
            "Type": {
                "select": {
                    "name": activity.get("type", activity.get("sport_type", "Unknown"))
                }
            }
        }
        
        # Add date if available
        # Strava returns ISO 8601 format which is compatible with Notion's date format
        if "start_date" in activity and activity["start_date"]:
            properties["Date"] = {
                "date": {
                    "start": activity["start_date"]
                }
            }
        
        # Add distance if available (convert meters to kilometers)
        if "distance" in activity:
            properties["Distance (km)"] = {
                "number": round(activity["distance"] / 1000, 2)
            }
        
        # Add duration if available (convert seconds to minutes)
        if "moving_time" in activity:
            properties["Duration (min)"] = {
                "number": round(activity["moving_time"] / 60, 1)
            }
        
        # Add elevation gain if available
        if "total_elevation_gain" in activity:
            properties["Elevation (m)"] = {
                "number": round(activity["total_elevation_gain"], 0)
            }
        
        # Add average heart rate if available
        if "average_heartrate" in activity:
            properties["Avg Heart Rate"] = {
                "number": round(activity["average_heartrate"], 0)
            }
        
        # Add Strava ID as external reference
        if "id" in activity:
            properties["Strava ID"] = {
                "number": activity["id"]
            }
        
        return properties
    
    def find_activity_by_strava_id(self, strava_id: int) -> Optional[Dict]:
        """
        Find a Notion page by Strava activity ID.
        
        Args:
            strava_id: The Strava activity ID
            
        Returns:
            Notion page object if found, None otherwise
        """
        filter_params = {
            "property": "Strava ID",
            "number": {
                "equals": strava_id
            }
        }
        
        results = self.query_database(filter_params)
        return results[0] if results else None
