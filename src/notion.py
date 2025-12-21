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

    def __init__(self, token: Optional[str] = None, activities_db_id: Optional[str] = None,
                 planned_db_id: Optional[str] = None):
        """
        Initialize the Notion client.

        Args:
            token: Notion integration token (defaults to NOTION_TOKEN env var)
            activities_db_id: Activities database ID (defaults to NOTION_ACTIVITIES_DB_ID env var)
            planned_db_id: Planned activities database ID (defaults to NOTION_PLANNED_DB_ID env var)
        """
        self.token = token or os.getenv("NOTION_TOKEN")
        self.activities_db_id = activities_db_id or os.getenv("NOTION_ACTIVITIES_DB_ID")
        self.planned_db_id = planned_db_id or os.getenv("NOTION_PLANNED_DB_ID")
        self.database_id = self.activities_db_id  # For backwards compatibility
        
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for Notion API requests."""
        if not self.token:
            raise ValueError("Missing Notion token")
            
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.NOTION_VERSION,
            "Content-Type": "application/json"
        }
    
    def query_database(self, filter_params: Optional[Dict] = None,
                      database_id: Optional[str] = None) -> List[Dict]:
        """
        Query a Notion database.

        Args:
            filter_params: Optional filter parameters for the query
            database_id: Database ID to query (defaults to activities_db_id)

        Returns:
            List of page objects from the database
        """
        db_id = database_id or self.activities_db_id
        if not db_id:
            raise ValueError("Missing Notion database ID")

        url = f"{self.BASE_URL}/databases/{db_id}/query"
        headers = self._get_headers()

        payload = {}
        if filter_params:
            payload["filter"] = filter_params

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        return response.json().get("results", [])
    
    def create_page(self, properties: Dict, database_id: Optional[str] = None) -> Dict:
        """
        Create a new page in a Notion database.

        Args:
            properties: Dictionary of page properties
            database_id: Database ID (defaults to activities_db_id)

        Returns:
            Created page object
        """
        db_id = database_id or self.activities_db_id
        if not db_id:
            raise ValueError("Missing Notion database ID")

        url = f"{self.BASE_URL}/pages"
        headers = self._get_headers()

        payload = {
            "parent": {"database_id": db_id},
            "properties": properties
        }

        # DEBUG: Print payload details
        print(f"  [DEBUG] Creating page in database: {db_id}")
        print(f"  [DEBUG] Number of properties: {len(properties)}")
        print(f"  [DEBUG] Property keys: {list(properties.keys())}")

        # Print each property in detail
        import json
        print(f"  [DEBUG] Full payload:")
        print(json.dumps(payload, indent=2))

        response = requests.post(url, headers=headers, json=payload)

        # DEBUG: Print response details if error
        if not response.ok:
            print(f"  [DEBUG] Response status: {response.status_code}")
            print(f"  [DEBUG] Response body: {response.text}")

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
    
    def activity_to_properties(self, activity: Dict, notion_sport_type: str = None) -> Dict:
        """
        Convert a Strava activity to Notion page properties with sport-specific fields.

        Args:
            activity: Strava activity dictionary
            notion_sport_type: Pre-converted Notion sport type (e.g., "Bike" instead of "Ride")

        Returns:
            Dictionary of Notion properties
        """
        # Get sport type from Strava (will be "Ride", "Run", or "Swim")
        strava_sport_type = activity.get("sport_type") or activity.get("type", "Unknown")

        # Use provided Notion sport type or default to Strava type
        # This allows "Ride" -> "Bike" conversion
        display_sport_type = notion_sport_type if notion_sport_type else strava_sport_type

        # DEBUG: Print activity details
        print(f"  [DEBUG] Converting activity to properties:")
        print(f"  [DEBUG]   Strava sport type: {strava_sport_type}")
        print(f"  [DEBUG]   Notion sport type: {display_sport_type}")
        print(f"  [DEBUG]   Activity name: {activity.get('name', 'Untitled Activity')}")

        # Base properties common to all activities
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
            # # Maps to "Color Select" field in your Notion (Run, Swim, Bike, etc.)
            # "Color Select": {
            #     "select": {
            #         "name": display_sport_type
            #     }
            # }
        }

        # Add date if available (Strava returns ISO 8601 format)
        if "start_date" in activity and activity["start_date"]:
            properties["Date"] = {
                "date": {
                    "start": activity["start_date"]
                }
            }

        # Add Strava ID as external reference for duplicate prevention
        if "id" in activity:
            properties["Strava ID"] = {
                "number": activity["id"]
            }

        # Sport-specific field mappings (use Strava type for logic)
        if strava_sport_type == "Run":
            sport_props = self._get_run_properties(activity)
            print(f"  [DEBUG]   Added {len(sport_props)} run-specific properties")
            properties.update(sport_props)
        elif strava_sport_type == "Ride":
            sport_props = self._get_ride_properties(activity)
            print(f"  [DEBUG]   Added {len(sport_props)} ride-specific properties")
            properties.update(sport_props)
        elif strava_sport_type == "Swim":
            sport_props = self._get_swim_properties(activity)
            print(f"  [DEBUG]   Added {len(sport_props)} swim-specific properties")
            properties.update(sport_props)

        print(f"  [DEBUG]   Total properties to send: {len(properties)}")

        return properties

    def _get_run_properties(self, activity: Dict) -> Dict:
        """
        Get running-specific properties from Strava activity.

        Args:
            activity: Strava activity dictionary

        Returns:
            Dictionary of run-specific Notion properties
        """
        properties = {}

        # Distance (meters to kilometers)
        if "distance" in activity:
            properties["Distance (km)"] = {
                "number": round(activity["distance"] / 1000, 2)
            }

        # Duration (seconds to minutes)
        if "moving_time" in activity:
            properties["Duration (min)"] = {
                "number": round(activity["moving_time"] / 60, 1)
            }

        # Average pace (min/km) - stored as number for calculations
        if "distance" in activity and "moving_time" in activity and activity["distance"] > 0:
            pace_min_per_km = (activity["moving_time"] / 60) / (activity["distance"] / 1000)
            properties["Average pace"] = {
                "number": round(pace_min_per_km, 2)
            }

        # Pace (text format for display, e.g., "5:30 /km")
        if "distance" in activity and "moving_time" in activity and activity["distance"] > 0:
            pace_min_per_km = (activity["moving_time"] / 60) / (activity["distance"] / 1000)
            pace_minutes = int(pace_min_per_km)
            pace_seconds = int((pace_min_per_km - pace_minutes) * 60)
            properties["Pace"] = {
                "rich_text": [
                    {
                        "text": {
                            "content": f"{pace_minutes}:{pace_seconds:02d} /km"
                        }
                    }
                ]
            }

        # Elevation gain
        if "total_elevation_gain" in activity:
            properties["Elevation Gain (m)"] = {
                "number": round(activity["total_elevation_gain"], 0)
            }

        # Heart rate - using your field name "Heart Rate Avg"
        if "average_heartrate" in activity:
            properties["Heart Rate Avg"] = {
                "number": round(activity["average_heartrate"], 0)
            }

        # Max heart rate
        if "max_heartrate" in activity:
            properties["Heart Rate Max"] = {
                "number": round(activity["max_heartrate"], 0)
            }

        # Average cadence
        if "average_cadence" in activity:
            properties["Average Cadence"] = {
                "number": round(activity["average_cadence"] * 2, 0)  # Strava returns steps per second, multiply by 2 for SPM
            }

        # Calories
        if "calories" in activity:
            properties["Calories"] = {
                "number": round(activity["calories"], 0)
            }

        return properties

    def _get_ride_properties(self, activity: Dict) -> Dict:
        """
        Get cycling-specific properties from Strava activity.

        Args:
            activity: Strava activity dictionary

        Returns:
            Dictionary of cycling-specific Notion properties
        """
        properties = {}

        # Distance (meters to kilometers)
        if "distance" in activity:
            properties["Distance (km)"] = {
                "number": round(activity["distance"] / 1000, 2)
            }

        # Duration (seconds to minutes)
        if "moving_time" in activity:
            properties["Duration (min)"] = {
                "number": round(activity["moving_time"] / 60, 1)
            }

        # Speed (km/h) - calculated from distance and time
        if "distance" in activity and "moving_time" in activity and activity["moving_time"] > 0:
            speed_kmh = (activity["distance"] / 1000) / (activity["moving_time"] / 3600)
            properties["Speed (km/h)"] = {
                "number": round(speed_kmh, 2)
            }

        # Elevation gain
        if "total_elevation_gain" in activity:
            properties["Elevation Gain (m)"] = {
                "number": round(activity["total_elevation_gain"], 0)
            }

        # Heart rate - using your field name "Heart Rate Avg"
        if "average_heartrate" in activity:
            properties["Heart Rate Avg"] = {
                "number": round(activity["average_heartrate"], 0)
            }

        # Max heart rate
        if "max_heartrate" in activity:
            properties["Heart Rate Max"] = {
                "number": round(activity["max_heartrate"], 0)
            }

        # Average power
        if "average_watts" in activity:
            properties["Power Avg (Watts)"] = {
                "number": round(activity["average_watts"], 0)
            }

        # Max power
        if "max_watts" in activity:
            properties["Power Max (Watts)"] = {
                "number": round(activity["max_watts"], 0)
            }

        # Average cadence
        if "average_cadence" in activity:
            properties["Average Cadence"] = {
                "number": round(activity["average_cadence"], 0)  # RPM for cycling
            }

        # Calories
        if "calories" in activity:
            properties["Calories"] = {
                "number": round(activity["calories"], 0)
            }

        return properties

    def _get_swim_properties(self, activity: Dict) -> Dict:
        """
        Get swimming-specific properties from Strava activity.

        Args:
            activity: Strava activity dictionary

        Returns:
            Dictionary of swim-specific Notion properties
        """
        properties = {}

        # Distance (meters)
        if "distance" in activity:
            properties["Distance (m)"] = {
                "number": round(activity["distance"], 0)
            }

        # Duration (seconds to minutes)
        if "moving_time" in activity:
            properties["Duration (min)"] = {
                "number": round(activity["moving_time"] / 60, 1)
            }

        # Swim Pace (min/100m) - as text format (e.g., "1:45 /100m")
        if "distance" in activity and "moving_time" in activity and activity["distance"] > 0:
            pace_min_per_100m = (activity["moving_time"] / 60) / (activity["distance"] / 100)
            pace_minutes = int(pace_min_per_100m)
            pace_seconds = int((pace_min_per_100m - pace_minutes) * 60)
            properties["Swim Pace (min/100m)"] = {
                "rich_text": [
                    {
                        "text": {
                            "content": f"{pace_minutes}:{pace_seconds:02d} /100m"
                        }
                    }
                ]
            }

        # Heart rate (if available with swim tracking device)
        if "average_heartrate" in activity:
            properties["Heart Rate Avg"] = {
                "number": round(activity["average_heartrate"], 0)
            }

        # Max heart rate
        if "max_heartrate" in activity:
            properties["Heart Rate Max"] = {
                "number": round(activity["max_heartrate"], 0)
            }

        # Stroke rate (strokes per minute)
        if "average_cadence" in activity:
            properties["Stroke Rate"] = {
                "number": round(activity["average_cadence"], 0)
            }

        # Calories
        if "calories" in activity:
            properties["Calories"] = {
                "number": round(activity["calories"], 0)
            }

        return properties
    
    def find_activity_by_strava_id(self, strava_id: int) -> Optional[Dict]:
        """
        Find a Notion page in Activities database by Strava activity ID.

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

        results = self.query_database(filter_params, database_id=self.activities_db_id)
        return results[0] if results else None

    def find_planned_activity(self, sport_type: str, date: str) -> Optional[Dict]:
        """
        Find a matching planned activity by sport type and date.

        Args:
            sport_type: The sport type (Bike, Run, Swim) - already converted from Strava format
            date: The activity date in ISO 8601 format

        Returns:
            Notion page object if found, None otherwise
        """
        # Extract just the date part (YYYY-MM-DD) from ISO 8601 datetime
        date_only = date.split("T")[0] if "T" in date else date

        # Using your actual Planning Database field names:
        # - "Sport relation" for the sport type (select field)
        # - "Date" for the date
        filter_params = {
            "and": [
                {
                    "property": "Sport relation",
                    "select": {
                        "equals": sport_type
                    }
                },
                {
                    "property": "Date",
                    "date": {
                        "equals": date_only
                    }
                }
            ]
        }

        results = self.query_database(filter_params, database_id=self.planned_db_id)
        return results[0] if results else None

    def link_activity_to_planned(self, activity_page_id: str, planned_page_id: str) -> Dict:
        """
        Link an activity to its planned activity.

        Args:
            activity_page_id: The ID of the activity page (in Training Log)
            planned_page_id: The ID of the planned activity page (in Planning Database)

        Returns:
            Updated activity page object
        """
        # Using your actual Training Log field name: "Linked Planned Workout"
        properties = {
            "Linked Planned Workout": {
                "relation": [
                    {"id": planned_page_id}
                ]
            }
        }

        return self.update_page(activity_page_id, properties)

    def mark_planned_as_done(self, planned_page_id: str) -> Dict:
        """
        Update a planned activity's selection status to "Done".

        Args:
            planned_page_id: The ID of the planned activity page

        Returns:
            Updated planned activity page object
        """
        # Using your actual Planning Database field name: "Selection status" (select field, not status field)
        properties = {
            "Selection status": {
                "select": {
                    "name": "Done"
                }
            }
        }

        return self.update_page(planned_page_id, properties)
