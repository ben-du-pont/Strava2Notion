"""
Sync orchestration module.

Main script that orchestrates the sync between Strava and Notion.
"""

import logging
from typing import Dict
from datetime import datetime, timedelta
from strava import get_strava_client
from notion import get_notion_client


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Map Strava sport types to our simplified categories
SPORT_TYPE_MAP = {
    'Run': 'Run',
    'TrailRun': 'Run',
    'VirtualRun': 'Run',
    'Ride': 'Ride',
    'VirtualRide': 'Ride',
    'MountainBikeRide': 'Ride',
    'GravelRide': 'Ride',
    'EBikeRide': 'Ride',
    'Swim': 'Swim',
    'OpenWaterSwim': 'Swim',
}


def get_sport_type(activity: Dict) -> str:
    """
    Determine the sport type category for an activity.

    Args:
        activity: Strava activity dictionary

    Returns:
        str: Sport type (Run, Ride, Swim, or Other)
    """
    strava_type = activity.get('type', '')
    sport_type = activity.get('sport_type', strava_type)

    # Map to our categories
    return SPORT_TYPE_MAP.get(sport_type, 'Other')


def sync_activity(activity: Dict, notion_client) -> bool:
    """
    Sync a single Strava activity to Notion.

    Args:
        activity: Strava activity dictionary
        notion_client: Configured Notion client

    Returns:
        bool: True if sync was successful, False otherwise
    """
    strava_id = activity.get('id')
    activity_name = activity.get('name', 'Untitled')

    try:
        # Check if activity already exists
        if notion_client.activity_exists(strava_id):
            logger.info(
                f"Skipping duplicate activity: {activity_name} (ID: {strava_id})")
            return True

        # Determine sport type
        sport_type = get_sport_type(activity)

        # Skip activities that aren't Run, Ride, or Swim
        if sport_type not in ['Run', 'Ride', 'Swim']:
            logger.info(
                f"Skipping unsupported activity type: {activity_name} (Type: {sport_type})")
            return True

        logger.info(f"Processing {sport_type} activity: {activity_name}")

        # Create activity in Notion
        activity_id = notion_client.create_activity(activity, sport_type)
        if not activity_id:
            logger.error(
                f"Failed to create activity in Notion: {activity_name}")
            return False

        # Find matching planned activity
        activity_date = activity.get('start_date')
        planned_id = notion_client.find_planned_activity(
            activity_date, sport_type)

        if planned_id:
            # Link to planned activity
            link_success = notion_client.link_to_planned_activity(
                activity_id, planned_id)
            if link_success:
                # Update planned activity status
                notion_client.update_planned_status(planned_id, "Done")

        logger.info(f"Successfully synced activity: {activity_name}")
        return True

    except Exception as e:
        logger.error(f"Error syncing activity {activity_name}: {e}")
        return False


def main():
    """
    Main sync function.

    Fetches recent Strava activities and syncs them to Notion.
    """
    logger.info("Starting Strava to Notion sync")

    try:
        # Initialize clients
        strava_client = get_strava_client()
        notion_client = get_notion_client()

        # Fetch activities from the last 7 days
        # Calculate epoch timestamp for 7 days ago
        seven_days_ago = datetime.now() - timedelta(days=7)
        after_timestamp = int(seven_days_ago.timestamp())

        logger.info(f"Fetching activities since {seven_days_ago.isoformat()}")
        activities = strava_client.get_activities(after=after_timestamp)

        if not activities:
            logger.info("No new activities to sync")
            return

        logger.info(f"Found {len(activities)} activities to process")

        # Process each activity
        success_count = 0
        failure_count = 0

        for activity in activities:
            if sync_activity(activity, notion_client):
                success_count += 1
            else:
                failure_count += 1

        # Log summary
        logger.info(
            f"Sync complete: {success_count} succeeded, {failure_count} failed")

    except Exception as e:
        logger.error(f"Fatal error during sync: {e}")
        raise


if __name__ == '__main__':
    main()
