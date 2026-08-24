"""
notion_planner.py — Create planned workout sessions in the Notion Planning DB.

Modes:
  --discover              Query Planning DB schema: prints all property types and select options.
  --sessions FILE         Create planned workout pages from a JSON session list.
  --dry-run               Print what would be created without making API calls.

Usage:
  python notion_planner.py --discover
  python notion_planner.py --sessions ../sessions.json --dry-run
  python notion_planner.py --sessions ../sessions.json

Session JSON format — list of objects, one per session:
  [
    {
      "name":               "Tempo Run — 2×2km @ 4:05/km",   # required
      "date":               "2026-03-24",                     # required (YYYY-MM-DD)
      "sport":              "Run",                            # required: Run | Bike | Swim
      "planned_distance_km": 9.0,                            # optional
      "planned_duration_min": 50,                            # optional
      "intensity_zone":     "Z4",                            # optional
      "focus":              "Speed work",                    # optional
      "expected_rpe":       7,                               # optional (1-10)
      "notes":              "2×2km @ 4:05/km, 120s rest",   # optional
      "original_plan":      "Full session description",      # optional
      "status":             "Planned",                       # optional
      "training_block":     "Marathon-Peak",                 # optional
      "time_of_day":        "Morning",                       # optional
      "part_of_brick":      false,                           # optional
      "brick_type":         ""                               # optional
    }
  ]
"""

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
sys.path.insert(0, os.path.dirname(__file__))
from notion import NotionClient


# ── Notion API helpers ──────────────────────────────────────────────────────

def get_database_schema(token: str, database_id: str) -> Dict:
    """Fetch raw database object from Notion API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
    }
    url = f"https://api.notion.com/v1/databases/{database_id}"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


# ── Discover mode ───────────────────────────────────────────────────────────

def discover(token: str, planned_db_id: str) -> None:
    """Print full schema of the Planning DB: property names, types, and select options."""
    print(f"Fetching Planning DB schema ({planned_db_id[:8]}…)\n")
    schema = get_database_schema(token, planned_db_id)

    properties = schema.get("properties", {})
    # Sort alphabetically
    sorted_props = sorted(properties.items(), key=lambda x: x[0].lower())

    # Find max name length for alignment
    max_len = max(len(name) for name, _ in sorted_props)

    print(f"{'Property':<{max_len}}  {'Type':<20}  Options / Notes")
    print("─" * (max_len + 60))

    for name, prop in sorted_props:
        ptype = prop.get("type", "unknown")
        notes = ""

        if ptype == "select":
            options = prop.get("select", {}).get("options", [])
            notes = ", ".join(f'"{o["name"]}"' for o in options) if options else "(no options yet)"
        elif ptype == "multi_select":
            options = prop.get("multi_select", {}).get("options", [])
            notes = ", ".join(f'"{o["name"]}"' for o in options) if options else "(no options yet)"
        elif ptype == "status":
            groups = prop.get("status", {}).get("groups", [])
            options = prop.get("status", {}).get("options", [])
            notes = ", ".join(f'"{o["name"]}"' for o in options) if options else "(no options)"
        elif ptype == "relation":
            db_id = prop.get("relation", {}).get("database_id", "")
            notes = f"→ DB {db_id[:8]}…" if db_id else ""
        elif ptype == "formula":
            expr = prop.get("formula", {}).get("expression", "")
            notes = f"formula: {expr[:60]}{'…' if len(expr) > 60 else ''}"
        elif ptype == "rollup":
            notes = "(rollup — read-only)"

        print(f"{name:<{max_len}}  {ptype:<20}  {notes}")

    print(f"\nTotal: {len(properties)} properties")
    print("\nNote: formula, rollup, and relation fields cannot be written directly.")
    print("      Use the types above when building session_to_properties().")


# ── Field value mappings ────────────────────────────────────────────────────

# Map shorthand zone (e.g. "Z2") to Notion select option label
ZONE_MAP = {
    "Z1": "Z1 Recovery",
    "Z2": "Z2 Endurance",
    "Z3": "Z3 Tempo",
    "Z4": "Z4 Threshold",
    "Z5": "Z5 VO₂",
}

# Map RPE number (1-10) to Notion select option
def rpe_label(value) -> str:
    if isinstance(value, str) and value in ("Low", "Medium", "High"):
        return value
    try:
        n = int(value)
        if n <= 3:
            return "Low"
        elif n <= 6:
            return "Medium"
        else:
            return "High"
    except (ValueError, TypeError):
        return str(value)

# Map internal block name to Notion select option
BLOCK_MAP = {
    "Marathon-Peak":        "Peak",
    "Triathlon Base Build": "Build 1",
    "HIM Race Block":       "Race Week",
    "Ironman Build":        "Build 2",
    "Ironman-Barcelona":    "Build 2",
    "Race Week":            "Race Week",
}


# ── Session → Notion properties ─────────────────────────────────────────────

def session_to_properties(client: NotionClient, session: Dict, schema: Dict) -> Dict:
    """
    Convert a session dict to a Notion properties dict.
    Only writes fields whose type we can handle; silently skips formula/rollup fields.

    Key schema facts (from --discover):
      Sport relation       → select  ("Run", "Bike", "Swim", ...)
      Expected RPE         → select  ("Low", "Medium", "High")
      Intensity Zone       → select  ("Z1 Recovery", ..., "Z5 VO₂")
      Training Block/Phase → select  ("Peak", "Taper", "Build 1", ...)
      Original Plan (Text) → formula — cannot write
      Status               → formula — cannot write
      Actual Dist/Dur      → rollup  — cannot write
    """
    props = {}
    p = schema.get("properties", {})

    def prop_type(name: str) -> str:
        return p.get(name, {}).get("type", "unknown")

    # ── Title ───────────────────────────────────────────────────────────────
    props["Name"] = {"title": [{"text": {"content": session["name"]}}]}

    # ── Date ────────────────────────────────────────────────────────────────
    props["Date"] = {"date": {"start": session["date"]}}

    # ── Sport (select, not relation despite the field name) ─────────────────
    props["Sport relation"] = {"select": {"name": session["sport"]}}

    # ── Selection status — always "Planned" on creation ─────────────────────
    props["Selection status"] = {"select": {"name": "Planned"}}

    # ── Planned Distance ────────────────────────────────────────────────────
    if session.get("planned_distance_km") is not None:
        props["Planned Distance (km)"] = {"number": float(session["planned_distance_km"])}

    # ── Planned Duration ────────────────────────────────────────────────────
    if session.get("planned_duration_min") is not None:
        props["Planned Duration (min)"] = {"number": float(session["planned_duration_min"])}

    # ── Expected RPE (select: Low / Medium / High) ──────────────────────────
    if session.get("expected_rpe") is not None:
        props["Expected RPE"] = {"select": {"name": rpe_label(session["expected_rpe"])}}

    # ── Intensity Zone (select with full label) ──────────────────────────────
    if session.get("intensity_zone"):
        raw = session["intensity_zone"]
        label = ZONE_MAP.get(raw, raw)  # expand "Z4" → "Z4 Threshold", else use as-is
        props["Intensity Zone"] = {"select": {"name": label}}

    # ── Focus (rich_text) ───────────────────────────────────────────────────
    if session.get("focus"):
        props["Focus"] = {"rich_text": [{"text": {"content": session["focus"]}}]}

    # ── Notes for Coach / Self (rich_text) ──────────────────────────────────
    if session.get("notes"):
        props["Notes for Coach / Self"] = {"rich_text": [{"text": {"content": session["notes"]}}]}

    # ── Training Block / Phase (select — map internal name → Notion option) ──
    if session.get("training_block"):
        raw = session["training_block"]
        label = BLOCK_MAP.get(raw, raw)
        props["Training Block / Phase"] = {"select": {"name": label}}

    # ── Time of Day (select) ─────────────────────────────────────────────────
    if session.get("time_of_day"):
        props["Time of Day"] = {"select": {"name": session["time_of_day"]}}

    # ── Location (select) ────────────────────────────────────────────────────
    if session.get("location"):
        props["Location"] = {"select": {"name": session["location"]}}

    # ── Part of Brick? (checkbox) ────────────────────────────────────────────
    if session.get("part_of_brick") is not None:
        props["Part of Brick?"] = {"checkbox": bool(session["part_of_brick"])}

    # ── Brick Type (select) ──────────────────────────────────────────────────
    if session.get("brick_type"):
        props["Brick Type"] = {"select": {"name": session["brick_type"]}}

    return props


# ── Duplicate detection ─────────────────────────────────────────────────────

def find_existing_session(client: NotionClient, date: str, sport: str) -> Optional[Dict]:
    """
    Check if a planned session with the same date + sport already exists in the Planning DB.
    Sport relation is a select field, so we can filter on both directly.
    """
    filter_params = {
        "and": [
            {"property": "Date",         "date":   {"equals": date}},
            {"property": "Sport relation","select": {"equals": sport}},
        ]
    }
    results = client.query_database(filter_params, database_id=client.planned_db_id)
    return results[0] if results else None


# ── Create sessions ─────────────────────────────────────────────────────────

SPORT_ICONS = {"Run": "🏃", "Bike": "🚴", "Swim": "🏊"}


def create_sessions(client: NotionClient, sessions: List[Dict], dry_run: bool, schema: Dict) -> None:
    """Create planned workout pages in Notion, skipping existing ones."""
    created = skipped = errors = 0

    for session in sessions:
        name = session.get("name", "Unnamed session")
        date = session.get("date", "")
        sport = session.get("sport", "")

        if not date or not sport:
            print(f"  [SKIP] Missing date or sport: {name}")
            skipped += 1
            continue

        print(f"\n→ {date} | {sport} | {name}")

        # Duplicate check
        existing = find_existing_session(client, date, sport)
        if existing:
            existing_title = "".join(
                p.get("text", {}).get("content", "")
                for p in existing.get("properties", {}).get("Name", {}).get("title", [])
            )
            print(f"  [SKIP] Already exists: '{existing_title}'")
            skipped += 1
            continue

        # Build properties
        try:
            props = session_to_properties(client, session, schema)
        except Exception as e:
            print(f"  [ERROR] Building properties: {e}")
            errors += 1
            continue

        icon = SPORT_ICONS.get(sport, "📋")

        if dry_run:
            print(f"  [DRY RUN] Would create with {len(props)} properties: {list(props.keys())}")
            created += 1
            continue

        # Create page
        try:
            page = client.create_page(props, database_id=client.planned_db_id, icon=icon)
            page_url = page.get("url", "")
            print(f"  [OK] Created: {page_url}")
            created += 1
        except requests.HTTPError as e:
            print(f"  [ERROR] API error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"         {e.response.text}")
            errors += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            errors += 1

    print(f"\n{'─'*40}")
    mode = "DRY RUN — " if dry_run else ""
    print(f"{mode}Created: {created} | Skipped: {skipped} | Errors: {errors}")


# ── List sessions ───────────────────────────────────────────────────────────

def list_sessions(client: NotionClient, from_date: str, to_date: str) -> None:
    """Query and print Planning DB sessions in a date range, with page IDs."""
    filter_params = {
        "and": [
            {"property": "Date", "date": {"on_or_after": from_date}},
            {"property": "Date", "date": {"on_or_before": to_date}},
        ]
    }
    results = client.query_database(filter_params, database_id=client.planned_db_id)

    if not results:
        print(f"No sessions found between {from_date} and {to_date}.")
        return

    # Sort by date
    def get_date(page):
        return page.get("properties", {}).get("Date", {}).get("date", {}).get("start", "")

    results.sort(key=get_date)
    print(f"{'Date':<12}  {'Sport':<6}  {'Status':<10}  {'Name':<45}  ID")
    print("─" * 110)
    for page in results:
        props = page.get("properties", {})
        date = get_date(page)[:10]
        sport = props.get("Sport relation", {}).get("select", {}).get("name", "—")
        status = props.get("Selection status", {}).get("select", {}).get("name", "—")
        name_parts = props.get("Name", {}).get("title", [])
        name = "".join(p.get("text", {}).get("content", "") for p in name_parts)[:44]
        page_id = page.get("id", "")
        print(f"{date:<12}  {sport:<6}  {status:<10}  {name:<45}  {page_id}")

    print(f"\nTotal: {len(results)} session(s)")


# ── Delete sessions ─────────────────────────────────────────────────────────

def delete_sessions(client: NotionClient, page_ids: List[str], dry_run: bool) -> None:
    """Archive (delete) Planning DB pages by ID."""
    for page_id in page_ids:
        if dry_run:
            print(f"  [DRY RUN] Would delete: {page_id}")
            continue
        try:
            client.delete_page(page_id)
            print(f"  [DELETED] {page_id}")
        except Exception as e:
            print(f"  [ERROR] {page_id}: {e}")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Manage planned workout sessions in Notion")
    parser.add_argument("--discover", action="store_true", help="Print Planning DB schema and exit")
    parser.add_argument("--sessions", metavar="FILE", help="JSON file with sessions to create")
    parser.add_argument("--list", action="store_true", help="List sessions in a date range")
    parser.add_argument("--from", dest="from_date", metavar="DATE", help="Start date (YYYY-MM-DD) for --list")
    parser.add_argument("--to", dest="to_date", metavar="DATE", help="End date (YYYY-MM-DD) for --list")
    parser.add_argument("--delete", nargs="+", metavar="PAGE_ID", help="Delete (archive) one or more sessions by page ID")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making API writes")
    args = parser.parse_args()

    token = os.getenv("NOTION_TOKEN")
    planned_db_id = os.getenv("NOTION_PLANNED_DB_ID")

    if not token:
        print("Error: NOTION_TOKEN not set in environment / .env")
        sys.exit(1)
    if not planned_db_id:
        print("Error: NOTION_PLANNED_DB_ID not set in environment / .env")
        sys.exit(1)

    if args.discover:
        discover(token, planned_db_id)
        return

    client = NotionClient()

    if args.list:
        if not args.from_date or not args.to_date:
            print("Error: --list requires --from DATE and --to DATE")
            sys.exit(1)
        list_sessions(client, args.from_date, args.to_date)
        return

    if args.delete:
        delete_sessions(client, args.delete, dry_run=args.dry_run)
        return

    if not args.sessions:
        parser.print_help()
        sys.exit(1)

    # Load sessions JSON
    sessions_path = args.sessions
    if not os.path.isabs(sessions_path):
        sessions_path = os.path.join(os.getcwd(), sessions_path)

    if not os.path.exists(sessions_path):
        print(f"Error: sessions file not found: {sessions_path}")
        sys.exit(1)

    with open(sessions_path) as f:
        sessions = json.load(f)

    if not isinstance(sessions, list):
        print("Error: sessions file must contain a JSON array")
        sys.exit(1)

    print(f"Loaded {len(sessions)} session(s) from {os.path.basename(sessions_path)}")
    if args.dry_run:
        print("Mode: DRY RUN (no Notion writes)\n")
    else:
        print()

    # Init client already initialized above
    # Fetch schema once (needed to determine property types)
    print("Fetching Planning DB schema…")
    schema = get_database_schema(token, planned_db_id)
    print(f"Schema loaded ({len(schema.get('properties', {}))} properties)\n")

    create_sessions(client, sessions, args.dry_run, schema)


if __name__ == "__main__":
    main()
