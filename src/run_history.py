"""
Generate a historical activity reference file for a given sport.

Modes:
  default      — full detail: fetches descriptions + laps per activity (used for run/bike)
  --volume-only — summary + weekly table + one-liner per session, no API detail calls
                  (used for swim: pace data is unreliable due to aids, drills, etc.)

Usage:
  python run_history.py                          # All runs since 2025-10-25 → 01_Run_History.md
  python run_history.py --sport swim             # All swims, volume-only → 01_Swim_History.md
  python run_history.py --sport run --volume-only
  python run_history.py --from 2025-11-01 --to 2026-03-20
  python run_history.py --output ../my_file.md
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from strava import StravaClient

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')

SPORT_DEFAULTS = {
    "run":  {"strava_types": ["Run"],                  "from": "2025-10-25", "out": "01_Run_History.md",  "volume_only": False},
    "swim": {"strava_types": ["Swim"],                 "from": "2025-11-01", "out": "01_Swim_History.md", "volume_only": True},
    "bike": {"strava_types": ["Ride", "VirtualRide"],  "from": "2026-03-01", "out": "01_Bike_History.md", "volume_only": False},
}

SPORT_LABELS = {"run": "Running", "swim": "Swimming", "bike": "Cycling"}


# ── Formatters ────────────────────────────────────────────────────────────────

def fmt_duration(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"

def fmt_pace_run(dist_m, time_s):
    if dist_m <= 0: return "—"
    p = (time_s / 60) / (dist_m / 1000)
    return f"{int(p)}:{int((p % 1) * 60):02d}/km"

def fmt_pace_swim(dist_m, time_s):
    if dist_m <= 0: return "—"
    p = (time_s / 60) / (dist_m / 100)
    return f"{int(p)}:{int((p % 1) * 60):02d}/100m"

def fmt_speed_bike(dist_m, time_s):
    if time_s <= 0: return "—"
    return f"{(dist_m / 1000) / (time_s / 3600):.1f} km/h"

def week_start(date_str):
    """Return the Monday of the week containing date_str (YYYY-MM-DD)."""
    d = datetime.fromisoformat(date_str[:10]).date()
    return d - timedelta(days=d.weekday())


# ── Activity formatter ────────────────────────────────────────────────────────

def format_activity_md(a, sport):
    date_str  = a.get("start_date_local", "")[:10]
    weekday   = datetime.fromisoformat(date_str).strftime("%a") if date_str else ""
    name      = a.get("name", "Untitled")
    dist_m    = a.get("distance", 0)
    moving    = a.get("moving_time", 0)
    elapsed   = a.get("elapsed_time", 0)
    elev      = a.get("total_elevation_gain", 0)
    avg_hr    = a.get("average_heartrate")
    max_hr    = a.get("max_heartrate")
    avg_cad   = a.get("average_cadence")
    avg_watts = a.get("average_watts")
    suffer    = a.get("suffer_score")
    calories  = a.get("calories")
    desc      = (a.get("description") or "").strip()
    laps      = a.get("laps") or []
    strava_id = a.get("id")

    # Header line
    if sport == "swim":
        dist_str = f"{dist_m:.0f} m"
        pace_str = fmt_pace_swim(dist_m, moving)
    elif sport == "bike":
        dist_str = f"{dist_m/1000:.2f} km"
        pace_str = fmt_speed_bike(dist_m, moving)
    else:
        dist_str = f"{dist_m/1000:.2f} km"
        pace_str = fmt_pace_run(dist_m, moving)

    lines = [f"### [{date_str} {weekday}] {name} — {dist_str}"]

    # Metrics line
    metrics = [f"`{pace_str}`", f"`{fmt_duration(moving)}`"]
    if avg_hr:
        metrics.append(f"`HR {avg_hr:.0f} avg`" + (f"` / {max_hr:.0f} max`" if max_hr else ""))
    if elev:
        metrics.append(f"`+{elev:.0f}m`")
    if avg_watts:
        metrics.append(f"`{avg_watts:.0f}W avg`")
    if suffer:
        metrics.append(f"`Suffer {suffer}`")
    if calories:
        metrics.append(f"`{calories:.0f} kcal`")
    lines.append("  ".join(metrics))
    lines.append(f"*Strava ID: {strava_id}*")

    # Description (Runna workout details)
    if desc:
        lines.append("")
        if sport == "run":
            lines.append("**Runna:**")
        elif sport == "swim":
            lines.append("**Workout notes:**")
        else:
            lines.append("**Notes:**")
        for dline in desc.splitlines():
            lines.append(f"> {dline}" if dline.strip() else ">")

    # Laps
    if laps:
        lines.append("")
        lap_parts = []
        for i, lap in enumerate(laps, 1):
            lm  = lap.get("distance", 0)
            lt  = lap.get("moving_time", 0)
            lhr = lap.get("average_heartrate")
            if sport == "swim":
                p = fmt_pace_swim(lm, lt)
                lap_parts.append(f"#{i} {lm:.0f}m @ {p}" + (f" HR{lhr:.0f}" if lhr else ""))
            elif sport == "bike":
                p = fmt_speed_bike(lm, lt)
                lw = lap.get("average_watts")
                lap_parts.append(f"#{i} {lm/1000:.2f}km @ {p}" + (f" {lw:.0f}W" if lw else ""))
            else:
                p = fmt_pace_run(lm, lt)
                lap_parts.append(f"#{i} {lm/1000:.2f}km @ {p}" + (f" HR{lhr:.0f}" if lhr else ""))
        lines.append("**Laps:** " + " | ".join(lap_parts))

    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


# ── Volume-only session list (no detail API calls) ───────────────────────────

def build_session_list(activities, sport):
    """One line per session — used when descriptions/laps are not meaningful."""
    lines = ["| Date | Name | Distance | Duration | Pace / Speed |",
             "|------|------|----------|----------|--------------|"]
    for a in activities:
        date_str = a.get("start_date_local", "")[:10]
        name     = a.get("name", "")
        dist_m   = a.get("distance", 0)
        moving   = a.get("moving_time", 0)
        if sport == "swim":
            dist_str = f"{dist_m:.0f} m"
            pace_str = fmt_pace_swim(dist_m, moving)
        elif sport == "bike":
            dist_str = f"{dist_m/1000:.2f} km"
            pace_str = fmt_speed_bike(dist_m, moving)
        else:
            dist_str = f"{dist_m/1000:.2f} km"
            pace_str = fmt_pace_run(dist_m, moving)
        lines.append(f"| {date_str} | {name} | {dist_str} | {fmt_duration(moving)} | {pace_str} |")
    return "\n".join(lines)


# ── Weekly table ──────────────────────────────────────────────────────────────

def build_weekly_table(activities, sport):
    weeks = defaultdict(lambda: {"runs": 0, "dist": 0.0, "long": 0.0, "times": [], "paces": []})

    for a in activities:
        ws = week_start(a.get("start_date_local", "1970-01-01")).isoformat()
        dist_m  = a.get("distance", 0)
        moving  = a.get("moving_time", 0)
        weeks[ws]["runs"]  += 1
        weeks[ws]["dist"]  += dist_m
        weeks[ws]["long"]   = max(weeks[ws]["long"], dist_m)
        if dist_m > 0 and moving > 0:
            weeks[ws]["paces"].append((dist_m, moving))

    header  = "| Week (Mon) | Sessions | Distance | Longest | Avg Pace |\n"
    header += "|------------|----------|----------|---------|----------|\n"
    rows = []
    for ws in sorted(weeks):
        w = weeks[ws]
        dist_km = w["dist"] / 1000
        long_km = w["long"] / 1000

        if w["paces"]:
            total_d = sum(p[0] for p in w["paces"])
            total_t = sum(p[1] for p in w["paces"])
            if sport == "swim":
                avg_pace = fmt_pace_swim(total_d, total_t)
            elif sport == "bike":
                avg_pace = fmt_speed_bike(total_d, total_t)
            else:
                avg_pace = fmt_pace_run(total_d, total_t)
        else:
            avg_pace = "—"

        if sport == "swim":
            rows.append(f"| {ws} | {w['runs']} | {w['dist']:.0f} m | {w['long']:.0f} m | {avg_pace} |")
        else:
            rows.append(f"| {ws} | {w['runs']} | {dist_km:.1f} km | {long_km:.1f} km | {avg_pace} |")

    return header + "\n".join(rows)


# ── Summary stats ─────────────────────────────────────────────────────────────

def build_summary(activities, sport, from_date, to_date):
    total_dist = sum(a.get("distance", 0) for a in activities)
    total_time = sum(a.get("moving_time", 0) for a in activities)
    n = len(activities)
    if not activities:
        return "No activities found."

    dates = sorted(a.get("start_date_local", "")[:10] for a in activities)
    first, last = dates[0], dates[-1]
    d1 = datetime.fromisoformat(first).date()
    d2 = datetime.fromisoformat(last).date()
    weeks = max(1, (d2 - d1).days // 7 + 1)

    longest = max(activities, key=lambda a: a.get("distance", 0))
    longest_dist = longest.get("distance", 0)
    longest_date = longest.get("start_date_local", "")[:10]

    if sport == "swim":
        dist_str  = f"{total_dist:.0f} m"
        long_str  = f"{longest_dist:.0f} m"
        avg_w_str = f"{total_dist/weeks:.0f} m/week"
    else:
        dist_str  = f"{total_dist/1000:.1f} km"
        long_str  = f"{longest_dist/1000:.1f} km"
        avg_w_str = f"{total_dist/1000/weeks:.1f} km/week"

    lines = [
        f"- **Activities**: {n} | **Total distance**: {dist_str} | **Total time**: {fmt_duration(total_time)}",
        f"- **Period**: {first} → {last} ({weeks} weeks)",
        f"- **Avg per week**: {avg_w_str}",
        f"- **Longest session**: {long_str} on {longest_date}",
    ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport",       choices=["run", "swim", "bike"], default="run")
    parser.add_argument("--from",        dest="date_from", metavar="YYYY-MM-DD")
    parser.add_argument("--to",          dest="date_to",   metavar="YYYY-MM-DD")
    parser.add_argument("--output",      metavar="PATH")
    parser.add_argument("--volume-only", dest="volume_only", action="store_true",
                        help="Skip per-activity detail calls; output summary + weekly table + session list only")
    args = parser.parse_args()

    cfg          = SPORT_DEFAULTS[args.sport]
    date_from    = args.date_from  or cfg["from"]
    date_to      = args.date_to    or date.today().isoformat()
    output_path  = args.output     or os.path.join(REPO_ROOT, cfg["out"])
    label        = SPORT_LABELS[args.sport]
    volume_only  = args.volume_only or cfg["volume_only"]

    print(f"Fetching {label} history: {date_from} → {date_to} ({'volume only' if volume_only else 'full detail'})")

    client = StravaClient()
    client.get_access_token()

    after  = int(datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc).timestamp())
    before = int((datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)).timestamp())

    print("Fetching activity list...", end=" ", flush=True)
    raw = client.get_activities(after=after, before=before, per_page=200)
    activities = [a for a in raw
                  if (a.get("sport_type") or a.get("type", "")) in cfg["strava_types"]]
    activities.sort(key=lambda a: a.get("start_date_local", ""))
    print(f"{len(activities)} activities found.")

    if not activities:
        print("Nothing to write.")
        return

    if volume_only:
        detailed = activities  # list-endpoint data is sufficient
    else:
        detailed = []
        for i, a in enumerate(activities, 1):
            print(f"  [{i}/{len(activities)}] {a.get('start_date_local','')[:10]} — {a.get('name','')}", end="\r", flush=True)
            detailed.append(client.get_activity_details(a["id"]))
        print()

    # Build markdown
    generated_on = datetime.now().strftime("%Y-%m-%d %H:%M")
    regen_flag   = f"--sport {args.sport}" + (" --volume-only" if volume_only else "")

    lines = [
        f"# {label} History — {date_from} to {date_to}",
        f"> One-time historical snapshot. Re-generate: `cd src && python run_history.py {regen_flag}`",
        f"> Claude: read this when asked about {args.sport} progression or session history.",
        f"",
        f"*Source: Strava | Generated: {generated_on}*",
        f"",
        f"---",
        f"",
        f"## Summary",
        f"",
        build_summary(detailed, args.sport, date_from, date_to),
        f"",
        f"---",
        f"",
        f"## Weekly Volume",
        f"",
        build_weekly_table(detailed, args.sport),
        f"",
        f"---",
        f"",
    ]

    if volume_only:
        lines += [
            f"## Session List",
            f"",
            f"> Note: pace figures are informational only — they do not reflect effort accurately",
            f"> because aids (pull buoy, fins), drills, and rest intervals affect recorded pace.",
            f"",
            build_session_list(detailed, args.sport),
            f"",
            f"---",
            f"",
            f"## Progression Notes",
            f"",
            f"*Add manual context here — equipment used, technique milestones, coach feedback, etc.*",
            f"",
        ]
    else:
        lines += [
            f"## Full Log",
            f"",
        ]
        for a in detailed:
            lines.append(format_activity_md(a, args.sport))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"\nSaved to: {output_path}")
    print(f"File size: {os.path.getsize(output_path) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
