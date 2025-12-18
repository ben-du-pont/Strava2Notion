"""
Main synchronization script for syncing Strava activities to Notion.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict

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
    
    # Sync statistics
    stats = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0
    }
    
    # Process each activity
    for activity in triathlon_activities:
        try:
            activity_id = activity.get("id")
            activity_name = activity.get("name", "Untitled")
            activity_type = activity.get("type", activity.get("sport_type", "Unknown"))
            
            print(f"\nProcessing: {activity_name} ({activity_type})")
            
            if dry_run:
                print("  [DRY RUN] Would sync this activity")
                stats["skipped"] += 1
                continue
            
            # Check if activity already exists in Notion
            existing_page = notion_client.find_activity_by_strava_id(activity_id)
            
            # Convert activity to Notion properties
            properties = notion_client.activity_to_properties(activity)
            
            if existing_page:
                # Update existing page
                page_id = existing_page["id"]
                notion_client.update_page(page_id, properties)
                print(f"  ✓ Updated existing page")
                stats["updated"] += 1
            else:
                # Create new page
                notion_client.create_page(properties)
                print(f"  ✓ Created new page")
                stats["created"] += 1
                
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
        print("=" * 60)
        
        # Exit with error code if there were errors
        if stats["errors"] > 0:
            sys.exit(1)
            
    except Exception as e:
        print(f"\n✗ Sync failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
