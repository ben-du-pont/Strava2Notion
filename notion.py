"""
Notion API integration module.

Handles queries, inserts, and updates for Notion databases.
"""

import os
import logging
from typing import Dict, List, Optional, Any
from notion_client import Client


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class NotionClient:
    """Client for interacting with Notion databases."""
    
    def __init__(self, token: str, activities_db_id: str, planned_db_id: str):
        """
        Initialize the Notion client.
        
        Args:
            token: Notion integration token
            activities_db_id: ID of the Activities database
            planned_db_id: ID of the Planned Activities database
        """
        self.client = Client(auth=token)
        self.activities_db_id = activities_db_id
        self.planned_db_id = planned_db_id
    
    def activity_exists(self, strava_id: int) -> bool:
        """
        Check if an activity with the given Strava ID already exists.
        
        Args:
            strava_id: Strava activity ID to check
            
        Returns:
            bool: True if activity exists, False otherwise
        """
        try:
            response = self.client.databases.query(
                database_id=self.activities_db_id,
                filter={
                    "property": "Strava ID",
                    "number": {
                        "equals": strava_id
                    }
                }
            )
            
            exists = len(response.get('results', [])) > 0
            if exists:
                logger.info(f"Activity with Strava ID {strava_id} already exists in Notion")
            return exists
            
        except Exception as e:
            logger.error(f"Failed to check if activity exists: {e}")
            raise
    
    def create_activity(self, activity_data: Dict, sport_type: str) -> Optional[str]:
        """
        Create a new activity entry in Notion.
        
        Args:
            activity_data: Dictionary containing Strava activity data
            sport_type: Type of sport (Run, Ride, or Swim)
            
        Returns:
            str: ID of the created Notion page, or None if creation fails
        """
        try:
            # Common properties for all activities
            properties = {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": activity_data.get('name', 'Untitled Activity')
                            }
                        }
                    ]
                },
                "Strava ID": {
                    "number": activity_data.get('id')
                },
                "Type": {
                    "select": {
                        "name": sport_type
                    }
                },
                "Date": {
                    "date": {
                        "start": activity_data.get('start_date')
                    }
                },
                "Distance": {
                    "number": activity_data.get('distance', 0) / 1000  # Convert meters to km
                },
                "Duration": {
                    "number": activity_data.get('moving_time', 0) / 60  # Convert seconds to minutes
                },
                "Elevation": {
                    "number": activity_data.get('total_elevation_gain', 0)
                }
            }
            
            # Add sport-specific properties
            if sport_type == "Run":
                # Running-specific fields
                avg_speed_kmh = (activity_data.get('average_speed', 0) * 3.6) if activity_data.get('average_speed') else 0
                properties["Average Pace"] = {
                    "number": (60 / avg_speed_kmh) if avg_speed_kmh > 0 else 0  # min/km
                }
                if activity_data.get('average_heartrate'):
                    properties["Average HR"] = {
                        "number": activity_data.get('average_heartrate')
                    }
                if activity_data.get('average_cadence'):
                    properties["Cadence"] = {
                        "number": activity_data.get('average_cadence') * 2  # Convert to steps per minute
                    }
                    
            elif sport_type == "Ride":
                # Cycling-specific fields
                avg_speed_kmh = activity_data.get('average_speed', 0) * 3.6 if activity_data.get('average_speed') else 0
                properties["Average Speed"] = {
                    "number": avg_speed_kmh
                }
                if activity_data.get('average_watts'):
                    properties["Average Power"] = {
                        "number": activity_data.get('average_watts')
                    }
                if activity_data.get('average_heartrate'):
                    properties["Average HR"] = {
                        "number": activity_data.get('average_heartrate')
                    }
                    
            elif sport_type == "Swim":
                # Swimming-specific fields
                avg_speed_mps = activity_data.get('average_speed', 0)
                if avg_speed_mps > 0:
                    pace_per_100m = (100 / avg_speed_mps) / 60  # minutes per 100m
                    properties["Average Pace"] = {
                        "number": pace_per_100m
                    }
            
            # Create the page
            response = self.client.pages.create(
                parent={"database_id": self.activities_db_id},
                properties=properties
            )
            
            page_id = response['id']
            logger.info(f"Successfully created {sport_type} activity in Notion: {activity_data.get('name')}")
            return page_id
            
        except Exception as e:
            logger.error(f"Failed to create activity in Notion: {e}")
            return None
    
    def find_planned_activity(self, activity_date: str, sport_type: str) -> Optional[str]:
        """
        Find a matching planned activity based on date and sport type.
        
        Args:
            activity_date: ISO format date string
            sport_type: Type of sport (Run, Ride, or Swim)
            
        Returns:
            str: ID of the matching planned activity page, or None if not found
        """
        try:
            # Extract just the date part (YYYY-MM-DD)
            date_only = activity_date.split('T')[0] if 'T' in activity_date else activity_date
            
            response = self.client.databases.query(
                database_id=self.planned_db_id,
                filter={
                    "and": [
                        {
                            "property": "Date",
                            "date": {
                                "equals": date_only
                            }
                        },
                        {
                            "property": "Type",
                            "select": {
                                "equals": sport_type
                            }
                        }
                    ]
                }
            )
            
            results = response.get('results', [])
            if results:
                planned_id = results[0]['id']
                logger.info(f"Found matching planned activity for {sport_type} on {date_only}")
                return planned_id
            else:
                logger.info(f"No matching planned activity found for {sport_type} on {date_only}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to find planned activity: {e}")
            return None
    
    def link_to_planned_activity(self, activity_id: str, planned_id: str) -> bool:
        """
        Link an activity to a planned activity.
        
        Args:
            activity_id: ID of the activity page
            planned_id: ID of the planned activity page
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Update the activity to link to the planned activity
            self.client.pages.update(
                page_id=activity_id,
                properties={
                    "Planned Activity": {
                        "relation": [
                            {
                                "id": planned_id
                            }
                        ]
                    }
                }
            )
            
            logger.info(f"Successfully linked activity to planned activity")
            return True
            
        except Exception as e:
            logger.error(f"Failed to link activity to planned activity: {e}")
            return False
    
    def update_planned_status(self, planned_id: str, status: str = "Done") -> bool:
        """
        Update the status of a planned activity.
        
        Args:
            planned_id: ID of the planned activity page
            status: New status value (default: "Done")
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.client.pages.update(
                page_id=planned_id,
                properties={
                    "Status": {
                        "status": {
                            "name": status
                        }
                    }
                }
            )
            
            logger.info(f"Successfully updated planned activity status to {status}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update planned activity status: {e}")
            return False


def get_notion_client() -> NotionClient:
    """
    Create a Notion client from environment variables.
    
    Returns:
        NotionClient: Configured Notion client
        
    Raises:
        ValueError: If required environment variables are missing
    """
    token = os.getenv('NOTION_TOKEN')
    activities_db_id = os.getenv('NOTION_ACTIVITIES_DB_ID')
    planned_db_id = os.getenv('NOTION_PLANNED_DB_ID')
    
    if not all([token, activities_db_id, planned_db_id]):
        raise ValueError(
            "Missing required Notion environment variables: "
            "NOTION_TOKEN, NOTION_ACTIVITIES_DB_ID, NOTION_PLANNED_DB_ID"
        )
    
    return NotionClient(token, activities_db_id, planned_db_id)
