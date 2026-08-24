"""
Main synchronization script for syncing Strava activities to Notion.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

try:
    from strava import StravaClient
    from notion import NotionClient
except ImportError:
    # Handle case when running as a script
    import importlib.util
    import pathlib
    
    current_dir = pathlib.Path(__file__).parent.resolve()
    
    spec = importlib.util.spec_from_file_location("strava", current_dir / "strava.py")
    strava = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(strava)
    StravaClient = strava.StravaClient
    
    spec = importlib.util.spec_from_file_location("notion", current_dir / "notion.py")
    notion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notion)
    NotionClient = notion.NotionClient


def _resolve_description_mode(config, sport_type: str) -> str:
    """
    Per-sport Strava description policy.

    Bike and swim descriptions are worth nothing as they arrive — Zwift writes
    route names and "Leveled up today" — so ours replaces them. Runs are left
    alone when Strava already holds text, because that is usually Runna's own
    session detail (or Ben's own note) and it is worth more than ours.

    STRAVA_DESCRIPTION_MODE, if set, overrides every sport.
    """
    env_override = os.getenv("STRAVA_DESCRIPTION_MODE")
    if env_override:
        return env_override.lower()

    per_sport = config.get_option("strava_description_mode", {}) or {}
    return str(per_sport.get(sport_type, "empty_only")).lower()


def _write_strava_description(strava_client, activity_id: int, description: str,
                              mode: str, own_prefix: str = "") -> bool:
    """
    Write a planned workout description back to a Strava activity.

    Args:
        strava_client: Authenticated StravaClient instance
        activity_id: Strava activity ID to update
        description: Description text from the planned workout
        mode: "overwrite" | "empty_only" | "append" | "false"
        own_prefix: Marker identifying descriptions we wrote ourselves. Those are
            always replaceable, so a re-sync can correct a previous bad match
            even under empty_only.

    Returns:
        True if the description was written, False otherwise
    """
    if mode in ("false", "none", "off"):
        return False

    if mode == "overwrite":
        return strava_client.update_activity_description(activity_id, description)

    # Both empty_only and append need the current description first
    current = strava_client.get_activity_description(activity_id)

    if mode == "empty_only":
        ours = own_prefix and current.strip().startswith(own_prefix)
        if current and not ours:
            print(f"  ⓘ Strava description already set by another source — keeping it")
            return False
        return strava_client.update_activity_description(activity_id, description)

    if mode == "append":
        combined = f"{current}\n\n---\n{description}" if current else description
        return strava_client.update_activity_description(activity_id, combined)

    print(f"  [WARN] Unknown description mode '{mode}', skipping description write")
    return False


def sync_activities(days_back: int = 7, dry_run: bool = False) -> Dict[str, int]:
    """
    Sync Strava activities to Notion database.
    
    Args:
        days_back: Number of days to look back for activities (default: 7)
        dry_run: If True, don't actually create/update pages in Notion
        
    Returns:
        Dictionary with sync statistics (created, updated, skipped)
    """
    print(f"Starting sync for the last {days_back} days...")
    
    # Initialize clients
    strava_client = StravaClient()
    notion_client = NotionClient()
    
    # Calculate timestamp for activities filter
    after_date = datetime.now() - timedelta(days=days_back)
    after_timestamp = int(after_date.timestamp())
    
    # Fetch activities from Strava
    print("Fetching activities from Strava...")
    activities = strava_client.get_activities(after=after_timestamp)
    
    # Filter for triathlon activities
    triathlon_activities = strava_client.filter_triathlon_activities(activities)
    print(f"Found {len(triathlon_activities)} triathlon activities (Swim, Bike, Run)")
    
    # Description write-back policy is resolved per sport (see _resolve_description_mode)

    # Sync statistics
    stats = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "descriptions_written": 0,
    }
    
    # Process each activity
    for activity in triathlon_activities:
        try:
            activity_id = activity.get("id")
            activity_name = activity.get("name", "Untitled")
            # Get Strava sport type (Ride, Run, Swim)
            strava_type = activity.get("sport_type") or activity.get("type", "Unknown")
            activity_date = activity.get("start_date", "")

            # Convert to Notion sport type (Ride -> Bike, others stay the same)
            notion_type = strava_client.get_notion_sport_type(strava_type)

            print(f"\nProcessing: {activity_name} ({strava_type} -> {notion_type})")

            if dry_run:
                print("  [DRY RUN] Would sync this activity")
                stats["skipped"] += 1
                continue

            # DUPLICATE PREVENTION: Check if activity already exists in Notion
            existing_page = notion_client.find_activity_by_strava_id(activity_id)

            if existing_page:
                # Skip if already exists - do not update
                print(f"  ⊘ Skipped - activity already exists in Notion")
                stats["skipped"] += 1
                continue

            # Convert activity to Notion properties with sport-specific fields
            # Pass the Notion sport type so "Ride" becomes "Bike" in the Color Select field
            properties, emoji_icon = notion_client.activity_to_properties(activity, notion_sport_type=notion_type)

            # Create new activity page with emoji icon
            created_page = notion_client.create_page(properties, icon=emoji_icon)
            print(f"  ✓ Created new activity page")
            stats["created"] += 1

            # Try to find matching planned activity (using Notion sport type).
            # Distance and duration corroborate the date so a moved session
            # cannot be linked to whichever plan happens to be free.
            planned_activity = notion_client.find_planned_activity(
                notion_type,
                activity_date,
                actual_distance_km=(activity.get("distance") or 0) / 1000,
                actual_duration_min=(activity.get("moving_time") or 0) / 60,
            )

            if planned_activity:
                planned_page_id = planned_activity["id"]
                created_page_id = created_page["id"]

                # Link the training log to the planned workout (sets "Linked Planned Workout" in Training Log)
                notion_client.link_activity_to_planned(created_page_id, planned_page_id)
                print(f"  ✓ Linked training log to planned workout")

                # Also link from the planned workout side (sets "Training Log Entries" in Planning Database)
                notion_client.link_planned_to_activity(planned_page_id, created_page_id)
                print(f"  ✓ Updated planned workout with training log link")

                # Mark the planned activity as done
                notion_client.mark_planned_as_done(planned_page_id)
                print(f"  ✓ Marked planned activity as Done")

                # Write planned description back to Strava
                planned_desc = notion_client.get_planned_description(planned_activity)
                if planned_desc:
                    written = _write_strava_description(
                        strava_client, activity_id, planned_desc,
                        _resolve_description_mode(notion_client.config, notion_type),
                        own_prefix=notion_client.DESCRIPTION_PREFIX,
                    )
                    if written:
                        print(f"  ✓ Updated Strava description from planned workout")
                        stats["descriptions_written"] += 1
                else:
                    print(f"  ⓘ Planned workout has no description to copy")
            else:
                print(f"  ⓘ No matching planned activity found")

        except Exception as e:
            print(f"  ✗ Error processing activity: {str(e)}")
            stats["errors"] += 1
    
    return stats


def main():
    """Main entry point for the sync script."""
    # Parse command line arguments
    try:
        days_back = int(os.getenv("DAYS_BACK", "7"))
    except (ValueError, TypeError):
        print("Warning: Invalid DAYS_BACK value, using default of 7 days")
        days_back = 7
    
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    
    print("=" * 60)
    print("Strava to Notion Triathlon Sync")
    print("=" * 60)
    
    try:
        stats = sync_activities(days_back=days_back, dry_run=dry_run)
        
        print("\n" + "=" * 60)
        print("Sync completed!")
        print(f"  Created: {stats['created']}")
        print(f"  Updated: {stats['updated']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Errors: {stats['errors']}")
        print(f"  Strava descriptions written: {stats['descriptions_written']}")
        print("=" * 60)
        
        # Exit with error code if there were errors
        if stats["errors"] > 0:
            sys.exit(1)
            
    except Exception as e:
        print(f"\n✗ Sync failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
