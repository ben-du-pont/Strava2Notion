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
    DESCRIPTION_PREFIX = "Claude Workout Description:"
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
    
    def get_page(self, page_id: str) -> Dict:
        """
        Fetch a single page.

        Args:
            page_id: The ID of the page to fetch

        Returns:
            Page object
        """
        response = requests.get(f"{self.BASE_URL}/pages/{page_id}", headers=self._get_headers())
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
        return f"{self.DESCRIPTION_PREFIX}\n{content}"

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

    # --- Planned-workout matching tuning -------------------------------------
    # Agreement between a planned and an actual session is symmetric:
    # min(r, 1/r) where r = planned / actual, so 0.5x and 2x score the same.
    OFFSET_MIN_AGREEMENT = 0.75     # a match on a different day must corroborate hard
    CONTESTED_MIN_AGREEMENT = 0.75  # ...and so must a same-day plan with rivals
    UNCONTESTED_MIN_AGREEMENT = 0.40  # lone same-day plan: a short session is still that session
    MIN_ACTIVITY_MINUTES = 5        # below this it is a junk/aborted recording

    @staticmethod
    def _week_bounds(day):
        """Monday..Sunday containing `day` — the planning week."""
        from datetime import timedelta
        monday = day - timedelta(days=day.weekday())
        return monday, monday + timedelta(days=6)

    @staticmethod
    def _agreement(planned_value: Optional[float], actual_value: Optional[float]) -> Optional[float]:
        """Symmetric agreement in (0, 1], or None when the metric is unusable."""
        if not planned_value or not actual_value or planned_value <= 0 or actual_value <= 0:
            return None
        ratio = planned_value / actual_value
        return min(ratio, 1 / ratio)

    def _plan_agreement(self, planned_workout: Dict, distance_km: Optional[float],
                        duration_min: Optional[float]) -> Optional[float]:
        """Best agreement across whichever of distance/duration the plan actually carries."""
        props = planned_workout.get("properties", {})
        scores = [
            self._agreement(props.get("Planned Distance (km)", {}).get("number"), distance_km),
            self._agreement(props.get("Planned Duration (min)", {}).get("number"), duration_min),
        ]
        scores = [s for s in scores if s is not None]
        return max(scores) if scores else None

    def find_planned_activity(self, sport_type: str, date: str,
                              actual_distance_km: Optional[float] = None,
                              actual_duration_min: Optional[float] = None,
                              max_days_diff: int = 3) -> Optional[Dict]:
        """
        Find the planned workout an activity corresponds to.

        Sport and date narrow the field; distance/duration decide. The rule is
        biased towards refusing rather than guessing, because a wrong link marks
        the wrong session Done and pushes every later activity onto the next
        free plan — a cascade that ran for nine days in August 2026.

        1. Candidates = same sport, same Mon-Sun planning week, not Done, not linked.
        2. Activities under MIN_ACTIVITY_MINUTES never match (junk recordings).
        3. Ranked by date distance, then by agreement — agreement breaks ties that
           the old `min()` resolved by Notion's arbitrary result order.
        4. Each candidate must clear an agreement floor:
             - different day            -> OFFSET_MIN_AGREEMENT
             - same day, rivals present -> CONTESTED_MIN_AGREEMENT
             - same day, sole candidate -> UNCONTESTED_MIN_AGREEMENT
           A shortened session on its own planned day is still that session; a
           50% shortfall against a plan on another day is a different session.
        5. A plan carrying neither distance nor duration can only match same-day.

        Args:
            sport_type: Notion sport type (Bike, Run, Swim) — already converted
            date: Activity date, ISO 8601
            actual_distance_km: Actual distance in km, for corroboration
            actual_duration_min: Actual moving time in minutes, for corroboration
            max_days_diff: Retained for compatibility; the window is the planning week

        Returns:
            The planned workout page, or None when nothing corroborates.
        """
        from datetime import datetime

        if actual_duration_min is not None and actual_duration_min < self.MIN_ACTIVITY_MINUTES:
            print(f"  ⓘ Activity under {self.MIN_ACTIVITY_MINUTES}min — not matching to a plan")
            return None

        date_only = date.split("T")[0] if "T" in date else date
        activity_date = datetime.fromisoformat(date_only).date()
        week_start, week_end = self._week_bounds(activity_date)

        filter_params = {
            "and": [
                {"property": "Sport relation", "select": {"equals": sport_type}},
                {"property": "Date", "date": {"on_or_after": week_start.isoformat()}},
                {"property": "Date", "date": {"on_or_before": week_end.isoformat()}},
            ]
        }
        available = self._filter_available_planned_workouts(
            self.query_database(filter_params, database_id=self.planned_db_id)
        )
        if not available:
            return None

        candidates = []
        for workout in available:
            planned_date_str = workout.get("properties", {}).get("Date", {}).get("date", {}).get("start", "")
            if not planned_date_str:
                continue
            planned_date = datetime.fromisoformat(planned_date_str.split("T")[0]).date()
            candidates.append({
                "workout": workout,
                "date": planned_date,
                "day_diff": abs((planned_date - activity_date).days),
                "agreement": self._plan_agreement(workout, actual_distance_km, actual_duration_min),
            })

        same_day_count = sum(1 for c in candidates if c["day_diff"] == 0)
        candidates.sort(key=lambda c: (c["day_diff"], -(c["agreement"] if c["agreement"] is not None else 0)))

        for cand in candidates:
            agreement, day_diff = cand["agreement"], cand["day_diff"]

            if agreement is None:
                # Nothing to corroborate with — only trust an exact-date hit.
                if day_diff == 0:
                    return cand["workout"]
                continue

            if day_diff == 0:
                floor = (self.CONTESTED_MIN_AGREEMENT if same_day_count > 1
                         else self.UNCONTESTED_MIN_AGREEMENT)
            else:
                floor = self.OFFSET_MIN_AGREEMENT

            if agreement >= floor:
                if day_diff:
                    print(f"  ⓘ Matched planned workout on {cand['date'].isoformat()} "
                          f"({day_diff} day(s) offset, agreement {agreement:.2f})")
                return cand["workout"]

        print("  ⓘ No planned workout corroborated by distance/duration — left unlinked")
        return None

    # "Skipped" is only ever set by hand, so it is a deliberate statement that
    # the session did not happen — never match an activity to one.
    UNAVAILABLE_STATUSES = ("Done", "Skipped")

    def _filter_available_planned_workouts(self, workouts: List[Dict]) -> List[Dict]:
        """
        Filter out planned workouts that are unavailable for matching.

        Args:
            workouts: List of planned workout page objects

        Returns:
            List of available (not done, not skipped, not linked) planned workouts
        """
        available = []

        for workout in workouts:
            properties = workout.get("properties", {})

            status = properties.get("Selection status", {}).get("select", {})
            if status and status.get("name") in self.UNAVAILABLE_STATUSES:
                continue  # Skip - already resolved (done, or deliberately skipped)

            # Check if there are already linked training log entries
            relations = properties.get("Training Log Entries", {}).get("relation", [])
            if relations:
                continue  # Skip - already has linked activities

            available.append(workout)

        return available

    @staticmethod
    def _same_page(a: str, b: str) -> bool:
        """Notion hands back dashed ids but accepts either form."""
        return a.replace("-", "").lower() == b.replace("-", "").lower()

    def _append_relation(self, page_id: str, property_name: str, related_id: str) -> Dict:
        """
        Add a relation while preserving the ones already there.

        Writing `"relation": [{"id": ...}]` replaces the whole array, which
        silently evicted the previous entry — a brick could never hold both its
        bike and its run, and the two sides of a link could drift apart.
        """
        page = self.get_page(page_id)
        existing = page.get("properties", {}).get(property_name, {}).get("relation", [])
        ids = [r["id"] for r in existing]

        if any(self._same_page(i, related_id) for i in ids):
            return page  # already linked

        ids.append(related_id)
        return self.update_page(page_id, {property_name: {"relation": [{"id": i} for i in ids]}})

    def link_activity_to_planned(self, activity_page_id: str, planned_page_id: str) -> Dict:
        """
        Record the activity on the planned workout ("Training Log Entries").

        Args:
            activity_page_id: The ID of the activity page (in Training Log database)
            planned_page_id: The ID of the planned workout page (in Planning Database)

        Returns:
            Updated Planning Database page object
        """
        return self._append_relation(planned_page_id, "Training Log Entries", activity_page_id)

    def link_planned_to_activity(self, planned_page_id: str, activity_page_id: str) -> Dict:
        """
        Record the planned workout on the activity ("Linked Planned Workout").

        Args:
            planned_page_id: The ID of the planned workout page (in Planning Database)
            activity_page_id: The ID of the completed activity page (in Training Log database)

        Returns:
            Updated Training Log page object
        """
        return self._append_relation(activity_page_id, "Linked Planned Workout", planned_page_id)

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
