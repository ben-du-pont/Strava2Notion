"""
Backfill cycling metrics for existing Notion pages that were synced before the
VirtualRide fix (PR #4 only patched strava.py, not notion.py).

For each Ride/VirtualRide in the given date window, finds the existing Notion
page by Strava ID and patches in the missing bike fields:
  - Speed (km/h)
  - Power Avg (Watts) / Power Max (Watts)
  - Average Cadence
  - (plus any other bike_fields values that may be missing)

Usage:
  cd src
  python backfill_rides.py            # last 60 days, dry run
  python backfill_rides.py --days 60  # explicit window
  python backfill_rides.py --commit   # actually write to Notion
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

sys.path.insert(0, os.path.dirname(__file__))
from strava import StravaClient
from notion import NotionClient


def build_bike_properties(notion_client: NotionClient, activity: dict) -> dict:
    """
    Build only the bike-specific Notion properties for an activity.
    Reuses the internal helper so field names come from config.yml.
    """
    strava_sport_type = activity.get("sport_type") or activity.get("type", "Unknown")
    return notion_client._get_sport_specific_properties(activity, "Bike", strava_sport_type)


def main():
    parser = argparse.ArgumentParser(description="Backfill cycling metrics in Notion")
    parser.add_argument("--days", type=int, default=60, help="How many days back to scan (default: 60)")
    parser.add_argument("--commit", action="store_true", help="Write changes to Notion (default: dry run)")
    args = parser.parse_args()

    dry_run = not args.commit

    print("=" * 60)
    print("Backfill Ride Metrics")
    print(f"  Window : last {args.days} days")
    print(f"  Mode   : {'DRY RUN' if dry_run else 'COMMIT'}")
    print("=" * 60)

    strava = StravaClient()
    notion = NotionClient()

    after_ts = int((datetime.now() - timedelta(days=args.days)).timestamp())
    print(f"\nFetching Strava activities since {datetime.fromtimestamp(after_ts).date()} ...")
    all_activities = strava.get_activities(after=after_ts, per_page=100)

    rides = [
        a for a in all_activities
        if (a.get("sport_type") or a.get("type")) in ("Ride", "VirtualRide")
    ]
    print(f"Found {len(rides)} ride(s) (Ride + VirtualRide)\n")

    stats = {"updated": 0, "not_found": 0, "errors": 0, "skipped": 0}

    for activity in rides:
        activity_id = activity["id"]
        name = activity.get("name", "Untitled")
        sport = activity.get("sport_type") or activity.get("type")
        date_str = activity.get("start_date", "")[:10]

        print(f"[{date_str}] {name} ({sport})")

        try:
            existing_page = notion.find_activity_by_strava_id(activity_id)
            if not existing_page:
                print(f"  ⊘ Not found in Notion — skipping")
                stats["not_found"] += 1
                continue

            page_id = existing_page["id"]
            props = build_bike_properties(notion, activity)

            if not props:
                print(f"  ⓘ No bike metrics available in Strava data — skipping")
                stats["skipped"] += 1
                continue

            field_summary = ", ".join(props.keys())
            print(f"  → Fields: {field_summary}")

            if dry_run:
                print(f"  [DRY RUN] Would update page {page_id}")
                stats["updated"] += 1
            else:
                try:
                    notion.update_page(page_id, props)
                    print(f"  ✓ Updated")
                    stats["updated"] += 1
                except Exception as e:
                    import requests as req_lib
                    if hasattr(e, 'response') and e.response is not None:
                        print(f"  ✗ Error: {e.response.text}")
                    else:
                        print(f"  ✗ Error: {e}")
                    stats["errors"] += 1
                    continue

        except Exception as e:
            print(f"  ✗ Error: {e}")
            stats["errors"] += 1

    print("\n" + "=" * 60)
    print(f"  {'Would update' if dry_run else 'Updated'} : {stats['updated']}")
    print(f"  Not in Notion : {stats['not_found']}")
    print(f"  No data       : {stats['skipped']}")
    print(f"  Errors        : {stats['errors']}")
    if dry_run:
        print("\n  Run with --commit to apply changes.")
    print("=" * 60)


if __name__ == "__main__":
    main()
