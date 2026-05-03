"""
Notion API integration module for managing triathlon training database.
"""

import os
import requests
from typing import Dict, List, Optional
from config_loader import ConfigLoader


class NotionClient:
    """Client for interacting with the Notion API."""

    BASE_URL = "https://api.notion.com/v1"
    NOTION_VERSION = "2022-06-28"

    def __init__(self, token: Optional[str] = None, activities_db_id: Optional[str] = None,
                 planned_db_id: Optional[str] = None, sports_db_id: Optional[str] = None,
                 config_path: Optional[str] = None):
        """
        Initialize the Notion client.

        Args:
            token: Notion integration token (defaults to NOTION_TOKEN env var)
            activities_db_id: Activities database ID (defaults to NOTION_ACTIVITIES_DB_ID env var)
            planned_db_id: Planned activities database ID (defaults to NOTION_PLANNED_DB_ID env var)
            sports_db_id: Sports database ID (defaults to NOTION_SPORTS_DB_ID env var)
            config_path: Path to config.yml (defaults to ../config.yml)
        """
        self.token = token or os.getenv("NOTION_TOKEN")
        self.activities_db_id = activities_db_id or os.getenv("NOTION_ACTIVITIES_DB_ID")
        self.planned_db_id = planned_db_id or os.getenv("NOTION_PLANNED_DB_ID")
        self.sports_db_id = sports_db_id or os.getenv("NOTION_SPORTS_DB_ID")
        self.database_id = self.activities_db_id  # For backwards compatibility

        # Load configuration
        self.config = ConfigLoader(config_path)

        # Cache for sport page IDs (sport_name -> page_id)
        self._sport_page_cache: Dict[str, str] = {}
        
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
    
    def create_page(self, properties: Dict, database_id: Optional[str] = None, icon: Optional[str] = None) -> Dict:
        """
        Create a new page in a Notion database.

        Args:
            properties: Dictionary of page properties
            database_id: Database ID (defaults to activities_db_id)
            icon: Optional emoji icon for the page

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

        # Add icon if provided
        if icon:
            payload["icon"] = {
                "type": "emoji",
                "emoji": icon
            }

        response = requests.post(url, headers=headers, json=payload)

        if not response.ok:
            print(f"  [WARN] Create page failed ({response.status_code}): {response.text}")

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
    
    def delete_page(self, page_id: str) -> Dict:
        """
        Delete (archive) a page via the Notion API.
        Note: the Notion API has no hard-delete endpoint — this archives the page,
        which removes it from all database views. Archived pages can be restored
        manually in Notion but are otherwise invisible.
        """
        url = f"{self.BASE_URL}/pages/{page_id}"
        headers = self._get_headers()
        response = requests.patch(url, headers=headers, json={"archived": True})
        response.raise_for_status()
        return response.json()

    def activity_to_properties(self, activity: Dict, notion_sport_type: str = None) -> tuple[Dict, str]:
        """
        Convert a Strava activity to Notion page properties with sport-specific fields.
        Uses configuration from config.yml for field mappings.

        Args:
            activity: Strava activity dictionary
            notion_sport_type: Pre-converted Notion sport type (e.g., "Bike" instead of "Ride")

        Returns:
            Tuple of (properties dictionary, emoji icon string)
        """
        # Get sport type from Strava (will be "Ride", "Run", or "Swim")
        strava_sport_type = activity.get("sport_type") or activity.get("type", "Unknown")

        # Use provided Notion sport type or default to Strava type
        # This allows "Ride" -> "Bike" conversion
        display_sport_type = notion_sport_type if notion_sport_type else strava_sport_type

        # Get emoji icon from config
        emoji_icon = self.config.get_sport_icon(display_sport_type) or "\U0001F3C3"

        properties = {}

        # Process common fields from config
        common_fields = self.config.get_common_fields()

        # Activity name (required - always synced as title)
        if "name" in common_fields:
            properties[common_fields["name"]] = {
                "title": [{
                    "text": {
                        "content": activity.get("name", "Untitled Activity")
                    }
                }]
            }

        # Start date
        if "start_date" in common_fields and activity.get("start_date"):
            properties[common_fields["start_date"]] = {
                "date": {
                    "start": activity["start_date"]
                }
            }

        # Strava ID
        if "id" in common_fields and activity.get("id"):
            properties[common_fields["id"]] = {
                "number": activity["id"]
            }

        # Sport Type relation (link to Sports database)
        if "sport_type_relation" in common_fields:
            notion_field_name = common_fields["sport_type_relation"]

            if not self.sports_db_id:
                print(f"  [WARN] NOTION_SPORTS_DB_ID not configured — skipping Sport Type relation")
            else:
                sport_page_id = self.find_sport_page_id(display_sport_type)
                if sport_page_id:
                    properties[notion_field_name] = {
                        "relation": [{"id": sport_page_id}]
                    }

        # Sport Type select field (optional alternative to relation)
        if "sport_type_select" in common_fields:
            properties[common_fields["sport_type_select"]] = {
                "select": {
                    "name": display_sport_type
                }
            }

        # Process additional simple fields from config automatically
        # This handles all the extra fields like description, location, weather, etc.
        simple_fields = [
            # Text fields
            ("description", "rich_text"),
            ("type", "select"),  # Activity type
            ("timezone", "rich_text"),
            ("external_id", "rich_text"),
            ("device_name", "rich_text"),
            ("location_city", "rich_text"),
            ("location_state", "rich_text"),
            ("location_country", "rich_text"),
            # Number fields
            ("upload_id", "number"),
            ("elapsed_time", "number"),
            ("utc_offset", "number"),
            ("elev_high", "number"),
            ("elev_low", "number"),
            ("max_speed", "number"),
            ("average_temp", "number"),
            ("kudos_count", "number"),
            ("comment_count", "number"),
            ("athlete_count", "number"),
            ("achievement_count", "number"),
            ("pr_count", "number"),
            ("photo_count", "number"),
            ("total_photo_count", "number"),
            ("weighted_average_watts", "number"),
            ("kilojoules", "number"),
            ("suffer_score", "number"),
            ("workout_type", "number"),
            # Boolean/checkbox fields
            ("trainer", "checkbox"),
            ("commute", "checkbox"),
            ("manual", "checkbox"),
            ("private", "checkbox"),
            ("flagged", "checkbox"),
            ("device_watts", "checkbox"),
            ("has_heartrate", "checkbox"),
        ]

        for field_key, field_type in simple_fields:
            if field_key in common_fields and activity.get(field_key) is not None:
                notion_field_name = common_fields[field_key]
                value = activity[field_key]

                if field_type == "rich_text":
                    properties[notion_field_name] = {
                        "rich_text": [{"text": {"content": str(value)}}]
                    }
                elif field_type == "number":
                    properties[notion_field_name] = {
                        "number": round(float(value), 2) if isinstance(value, (int, float)) else value
                    }
                elif field_type == "checkbox":
                    properties[notion_field_name] = {
                        "checkbox": bool(value)
                    }
                elif field_type == "select":
                    properties[notion_field_name] = {
                        "select": {"name": str(value)}
                    }

        # Add sport-specific properties
        sport_props = self._get_sport_specific_properties(activity, display_sport_type, strava_sport_type)
        properties.update(sport_props)

        return properties, emoji_icon

    def _get_sport_specific_properties(self, activity: Dict, display_sport_type: str, strava_sport_type: str) -> Dict:
        """
        Get sport-specific properties from Strava activity using config.yml mappings.

        Args:
            activity: Strava activity dictionary
            display_sport_type: Notion sport type (Run, Bike, Swim)
            strava_sport_type: Strava sport type (Run, Ride, Swim)

        Returns:
            Dictionary of sport-specific Notion properties
        """
        properties = {}

        # Get field mappings from config for this sport type
        sport_fields = self.config.get_sport_fields(display_sport_type)

        # Get conversion factors from config
        distance_divisor = self.config.get_distance_divisor()
        time_divisor = self.config.get_time_divisor()
        include_pace_suffix = self.config.should_include_pace_suffix()

        # Distance
        if "distance" in sport_fields and activity.get("distance"):
            properties[sport_fields["distance"]] = {
                "number": round(activity["distance"] / distance_divisor, 2)
            }

        # Moving time / Duration
        if "moving_time" in sport_fields and activity.get("moving_time"):
            properties[sport_fields["moving_time"]] = {
                "number": round(activity["moving_time"] / time_divisor, 1)
            }

        # Running-specific fields
        if strava_sport_type == "Run":
            # Average pace as number (min/km)
            if "average_pace_number" in sport_fields and activity.get("distance") and activity.get("moving_time"):
                if activity["distance"] > 0:
                    pace_min_per_km = (activity["moving_time"] / 60) / (activity["distance"] / 1000)
                    properties[sport_fields["average_pace_number"]] = {
                        "number": round(pace_min_per_km, 2)
                    }

            # Pace as formatted text
            if "pace_text" in sport_fields and activity.get("distance") and activity.get("moving_time"):
                if activity["distance"] > 0:
                    pace_min_per_km = (activity["moving_time"] / 60) / (activity["distance"] / 1000)
                    pace_minutes = int(pace_min_per_km)
                    pace_seconds = int((pace_min_per_km - pace_minutes) * 60)
                    pace_str = f"{pace_minutes}:{pace_seconds:02d}"
                    if include_pace_suffix:
                        pace_str += " /km"
                    properties[sport_fields["pace_text"]] = {
                        "rich_text": [{
                            "text": {"content": pace_str}
                        }]
                    }

            # Average cadence (steps per minute - Strava returns steps per second)
            if "average_cadence" in sport_fields and activity.get("average_cadence"):
                properties[sport_fields["average_cadence"]] = {
                    "number": round(activity["average_cadence"] * 2, 0)  # Convert to SPM
                }

        # Cycling-specific fields
        elif strava_sport_type in ("Ride", "VirtualRide"):
            # Average speed (km/h)
            if "average_speed" in sport_fields and activity.get("distance") and activity.get("moving_time"):
                if activity["moving_time"] > 0:
                    speed_kmh = (activity["distance"] / 1000) / (activity["moving_time"] / 3600)
                    properties[sport_fields["average_speed"]] = {
                        "number": round(speed_kmh, 2)
                    }

            # Average power
            if "average_watts" in sport_fields and activity.get("average_watts"):
                properties[sport_fields["average_watts"]] = {
                    "number": round(activity["average_watts"], 0)
                }

            # Max power
            if "max_watts" in sport_fields and activity.get("max_watts"):
                properties[sport_fields["max_watts"]] = {
                    "number": round(activity["max_watts"], 0)
                }

            # Average cadence (RPM for cycling)
            if "average_cadence" in sport_fields and activity.get("average_cadence"):
                properties[sport_fields["average_cadence"]] = {
                    "number": round(activity["average_cadence"], 0)
                }

        # Swimming-specific fields
        elif strava_sport_type == "Swim":
            # Swim pace as formatted text (min/100m)
            if "swim_pace_text" in sport_fields and activity.get("distance") and activity.get("moving_time"):
                if activity["distance"] > 0:
                    pace_min_per_100m = (activity["moving_time"] / 60) / (activity["distance"] / 100)
                    pace_minutes = int(pace_min_per_100m)
                    pace_seconds = int((pace_min_per_100m - pace_minutes) * 60)
                    properties[sport_fields["swim_pace_text"]] = {
                        "rich_text": [{
                            "text": {"content": f"{pace_minutes}:{pace_seconds:02d}"}
                        }]
                    }

            # Stroke rate (cadence for swimming)
            if "average_cadence" in sport_fields and activity.get("average_cadence"):
                properties[sport_fields["average_cadence"]] = {
                    "number": round(activity["average_cadence"], 0)
                }

        # Common fields across all sports (but sport-specific sections in config)

        # Elevation gain
        if "total_elevation_gain" in sport_fields and activity.get("total_elevation_gain"):
            properties[sport_fields["total_elevation_gain"]] = {
                "number": round(activity["total_elevation_gain"], 0)
            }

        # Average heart rate
        if "average_heartrate" in sport_fields and activity.get("average_heartrate"):
            properties[sport_fields["average_heartrate"]] = {
                "number": round(activity["average_heartrate"], 0)
            }

        # Max heart rate
        if "max_heartrate" in sport_fields and activity.get("max_heartrate"):
            properties[sport_fields["max_heartrate"]] = {
                "number": round(activity["max_heartrate"], 0)
            }

        # Calories
        if "calories" in sport_fields and activity.get("calories"):
            properties[sport_fields["calories"]] = {
                "number": round(activity["calories"], 0)
            }

        return properties

    def get_planned_description(self, planned_page: Dict) -> str:
        """
        Extract a human-readable description from a planned workout page.
        Combines the Focus and Notes for Coach / Self fields.

        Args:
            planned_page: Notion page object from the Planning database

        Returns:
            Formatted description string, or "" if both fields are empty
        """
        props = planned_page.get("properties", {})

        def extract_rich_text(field_name: str) -> str:
            parts = props.get(field_name, {}).get("rich_text", [])
            return "".join(p.get("text", {}).get("content", "") for p in parts).strip()

        focus = extract_rich_text("Focus")
        notes = extract_rich_text("Notes for Coach / Self")

        content = f"{focus}\n{notes}" if (focus and notes) else (focus or notes)
        if not content:
            return ""
        return f"Claude Workout Description:\n{content}"

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

    def find_planned_activity(self, sport_type: str, date: str, max_days_diff: int = 3) -> Optional[Dict]:
        """
        Find a matching planned activity by sport type and date with smart matching.

        Matching logic:
        1. First tries to find exact date match
        2. If not found, searches for activities within ±max_days_diff days
        3. Filters out workouts that are already marked as "Done"
        4. Filters out workouts that already have linked training log entries
        5. Returns the closest match by date

        Args:
            sport_type: The sport type (Bike, Run, Swim) - already converted from Strava format
            date: The activity date in ISO 8601 format
            max_days_diff: Maximum number of days difference to search (default: 3)

        Returns:
            Notion page object if found, None otherwise
        """
        from datetime import datetime, timedelta

        # Extract just the date part (YYYY-MM-DD) from ISO 8601 datetime
        date_only = date.split("T")[0] if "T" in date else date
        activity_date = datetime.fromisoformat(date_only)

        # Step 1: Try exact date match first
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

        # Filter out already completed/linked workouts
        available_results = self._filter_available_planned_workouts(results)

        if available_results:
            return available_results[0]

        # Step 2: Search within date range (±max_days_diff days)

        start_date = (activity_date - timedelta(days=max_days_diff)).isoformat()
        end_date = (activity_date + timedelta(days=max_days_diff)).isoformat()

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
                        "on_or_after": start_date
                    }
                },
                {
                    "property": "Date",
                    "date": {
                        "on_or_before": end_date
                    }
                }
            ]
        }

        results = self.query_database(filter_params, database_id=self.planned_db_id)

        # Filter out already completed/linked workouts
        available_results = self._filter_available_planned_workouts(results)

        if not available_results:
            return None

        # Step 3: Find the closest match by date
        def get_date_diff(planned_workout):
            """Calculate absolute difference in days between planned and actual activity."""
            planned_date_str = planned_workout.get("properties", {}).get("Date", {}).get("date", {}).get("start", "")
            if not planned_date_str:
                return float('inf')
            planned_date = datetime.fromisoformat(planned_date_str.split("T")[0])
            return abs((planned_date - activity_date).days)

        closest_match = min(available_results, key=get_date_diff)
        days_diff = get_date_diff(closest_match)

        planned_date = closest_match.get("properties", {}).get("Date", {}).get("date", {}).get("start", "")
        print(f"  ⓘ Matched planned workout on {planned_date} ({days_diff} day(s) offset)")

        return closest_match

    def _filter_available_planned_workouts(self, workouts: List[Dict]) -> List[Dict]:
        """
        Filter out planned workouts that are already completed or linked.

        Args:
            workouts: List of planned workout page objects

        Returns:
            List of available (not done, not linked) planned workouts
        """
        available = []

        for workout in workouts:
            properties = workout.get("properties", {})

            # Check if status is "Done"
            status = properties.get("Selection status", {}).get("select", {})
            if status and status.get("name") == "Done":
                continue  # Skip - already marked as done

            # Check if there are already linked training log entries
            relations = properties.get("Training Log Entries", {}).get("relation", [])
            if relations:
                continue  # Skip - already has linked activities

            available.append(workout)

        return available

    def link_activity_to_planned(self, activity_page_id: str, planned_page_id: str) -> Dict:
        """
        Link activity to planned workout by updating the Planning Database.

        This updates the Planning Database entry with the activity's ID in the
        "Training Log Entries" field.

        Args:
            activity_page_id: The ID of the activity page (in Training Log database)
            planned_page_id: The ID of the planned workout page (in Planning Database)

        Returns:
            Updated Planning Database page object
        """
        # Update the Planning Database with the activity ID
        properties = {
            "Training Log Entries": {
                "relation": [
                    {"id": activity_page_id}
                ]
            }
        }

        return self.update_page(planned_page_id, properties)

    def link_planned_to_activity(self, planned_page_id: str, activity_page_id: str) -> Dict:
        """
        Link planned workout to activity by updating the Training Log.

        This updates the Training Log entry with the planned workout's ID in the
        "Linked Planned Workout" field.

        Args:
            planned_page_id: The ID of the planned workout page (in Planning Database)
            activity_page_id: The ID of the completed activity page (in Training Log database)

        Returns:
            Updated Training Log page object
        """
        # Update the Training Log with the planned workout ID
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

    def find_sport_page_id(self, sport_name: str) -> Optional[str]:
        """
        Find a sport page ID by sport name from the Sports database.

        Args:
            sport_name: The sport name (e.g., "Run", "Bike", "Swim")

        Returns:
            Sport page ID if found, None otherwise
        """
        # Check cache first
        if sport_name in self._sport_page_cache:
            return self._sport_page_cache[sport_name]

        if not self.sports_db_id:
            print(f"  [WARNING] Sports database ID not configured, skipping Sport Type relation")
            return None

        # Query the Sports database for the matching sport name
        filter_params = {
            "property": "Name",
            "title": {
                "equals": sport_name
            }
        }

        results = self.query_database(filter_params, database_id=self.sports_db_id)

        if results:
            sport_page_id = results[0]["id"]
            # Cache the result
            self._sport_page_cache[sport_name] = sport_page_id
            return sport_page_id

        return None
