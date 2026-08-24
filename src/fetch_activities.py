"""
Fetch and display recent Strava activities at configurable detail levels.

Detail levels:
  summary  — list endpoint only: date, sport, distance, duration, pace/speed
  standard — + activity details: HR, elevation, cadence, laps, suffer score  [default]
  full     — + streams: HR evolution, pace/power curve, altitude profile, GPS, temperature

Usage:
  python fetch_activities.py [--from YYYY-MM-DD --to YYYY-MM-DD] [--days N] [--sport run|bike|swim] [--detail summary|standard|full]
  python fetch_activities.py --id STRAVA_ID [--detail standard|full]
"""

import argparse
import os
import sys
import yaml
from datetime import datetime, date, timezone, timedelta
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from strava import StravaClient

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

STREAM_TYPES = "time,heartrate,velocity_smooth,altitude,cadence,watts,latlng,temp,grade_smooth"
CONFIG_PATH  = os.path.join(os.path.dirname(__file__), '..', 'config.yml')


def load_zones():
    """Load training zones from config.yml."""
    try:
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("zones", {})
    except Exception:
        return {}


# ── Formatters ────────────────────────────────────────────────────────────────

def fmt_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"

def fmt_pace_run(distance_m: float, moving_time_s: int) -> str:
    if distance_m <= 0: return "—"
    pace = (moving_time_s / 60) / (distance_m / 1000)
    return f"{int(pace)}:{int((pace % 1) * 60):02d}/km"

def fmt_pace_swim(distance_m: float, moving_time_s: int) -> str:
    if distance_m <= 0: return "—"
    pace = (moving_time_s / 60) / (distance_m / 100)
    return f"{int(pace)}:{int((pace % 1) * 60):02d}/100m"

def fmt_speed_bike(distance_m: float, moving_time_s: int) -> str:
    if moving_time_s <= 0: return "—"
    return f"{(distance_m / 1000) / (moving_time_s / 3600):.1f} km/h"


# ── HR zone breakdown (zones loaded from config.yml) ─────────────────────────

ZONE_LABELS = ["Z1", "Z2", "Z3", "Z4", "Z5"]

def hr_zone_breakdown(hr_stream: list, time_stream: list, sport: str = "run") -> str:
    zones_cfg = load_zones().get(sport, {})
    if not zones_cfg or not hr_stream or not time_stream:
        return ""
    zone_ranges = [zones_cfg.get(z, [0, 0]) for z in ZONE_LABELS]
    counts = [0] * 5
    for i, hr in enumerate(hr_stream):
        if hr is None:
            continue
        dt = (time_stream[i] - time_stream[i - 1]) if i > 0 else 1
        for z, (lo, hi) in enumerate(zone_ranges):
            if lo <= hr < hi:
                counts[z] += dt
                break
    total = sum(counts) or 1
    parts = [f"{ZONE_LABELS[z]}: {fmt_duration(counts[z])} ({counts[z]/total*100:.0f}%)"
             for z in range(5) if counts[z] > 0]
    return "  HR Zones : " + " | ".join(parts)

def pace_splits_run(dist_stream: list, time_stream: list) -> str:
    """Per-km pace splits from streams."""
    if not dist_stream or not time_stream:
        return ""
    splits = []
    km = 1
    last_t = time_stream[0]
    last_d = dist_stream[0]
    for i, d in enumerate(dist_stream):
        if d >= km * 1000:
            elapsed = time_stream[i] - last_t
            splits.append(fmt_pace_run(d - last_d, elapsed))
            last_t = time_stream[i]
            last_d = d
            km += 1
            if km > 50:  # safety cap
                break
    if not splits:
        return ""
    return "  Km Splits : " + " | ".join(splits)

def altitude_profile(alt_stream: list) -> str:
    if not alt_stream:
        return ""
    valid = [a for a in alt_stream if a is not None]
    if not valid:
        return ""
    return (f"  Altitude  : {min(valid):.0f}m min / {max(valid):.0f}m max / "
            f"{max(valid) - min(valid):.0f}m range")

def power_stats(watts_stream: list) -> str:
    if not watts_stream:
        return ""
    valid = [w for w in watts_stream if w is not None and w > 0]
    if not valid:
        return ""
    avg = sum(valid) / len(valid)
    # Normalized power (4th power mean)
    np = (sum(w**4 for w in valid) / len(valid)) ** 0.25
    return f"  Power     : {avg:.0f}W avg / {np:.0f}W normalized / {max(valid):.0f}W max"

def gps_summary(latlng_stream: list) -> str:
    if not latlng_stream:
        return ""
    start = latlng_stream[0]
    end = latlng_stream[-1]
    return f"  GPS       : start {start[0]:.4f},{start[1]:.4f} → end {end[0]:.4f},{end[1]:.4f} ({len(latlng_stream)} points)"


# ── Display ───────────────────────────────────────────────────────────────────

def display_summary(a: dict) -> list[str]:
    sport = a.get("sport_type") or a.get("type", "?")
    is_bike = sport in ("Ride", "VirtualRide")
    sport_label = "BIKE (indoor)" if sport == "VirtualRide" else sport.upper()
    dist_m = a.get("distance", 0)
    moving = a.get("moving_time", 0)
    elapsed = a.get("elapsed_time", 0)
    date = a.get("start_date_local", "")[:10]
    name = a.get("name", "Untitled")

    lines = [
        f"  [{date}] {sport_label} — {name}  (id: {a.get('id')})",
        f"  Distance : {dist_m/1000:.2f} km" if sport != "Swim" else f"  Distance : {dist_m:.0f} m",
        f"  Duration : {fmt_duration(moving)} moving / {fmt_duration(elapsed)} elapsed",
    ]
    if sport == "Run":
        lines.append(f"  Pace     : {fmt_pace_run(dist_m, moving)}")
    elif is_bike:
        lines.append(f"  Speed    : {fmt_speed_bike(dist_m, moving)}")
    elif sport == "Swim":
        lines.append(f"  Pace     : {fmt_pace_swim(dist_m, moving)}")
    return lines


def display_standard(a: dict) -> list[str]:
    """Activity details (requires GET /activities/{id})."""
    sport = a.get("sport_type") or a.get("type", "?")
    is_bike = sport in ("Ride", "VirtualRide")
    lines = display_summary(a)

    avg_hr     = a.get("average_heartrate")
    max_hr     = a.get("max_heartrate")
    elevation  = a.get("total_elevation_gain", 0)
    avg_cad    = a.get("average_cadence")
    avg_watts  = a.get("average_watts")
    suffer     = a.get("suffer_score")
    calories   = a.get("calories")
    device     = a.get("device_name")
    description = (a.get("description") or "").strip()
    laps       = a.get("laps", [])
    temp       = a.get("average_temp")

    if elevation:
        lines.append(f"  Elevation : {elevation:.0f} m gain")
    if avg_hr:
        lines.append(f"  HR        : {avg_hr:.0f} avg" + (f" / {max_hr:.0f} max" if max_hr else ""))
    if avg_cad:
        cad_val = int(avg_cad * 2) if sport == "Run" else avg_cad
        unit = "spm" if sport == "Run" else ("spm" if sport == "Swim" else "rpm")
        lines.append(f"  Cadence   : {cad_val:.0f} {unit}")
    if avg_watts:
        lines.append(f"  Power     : {avg_watts:.0f}W avg")
    if calories:
        lines.append(f"  Calories  : {calories:.0f} kcal")
    if temp is not None:
        lines.append(f"  Temp      : {temp:.0f}°C")
    if suffer:
        lines.append(f"  Suffer    : {suffer}")
    if device:
        lines.append(f"  Device    : {device}")
    if description:
        lines.append(f"  Notes     : {description}")

    if laps:
        lap_lines = []
        for i, lap in enumerate(laps, 1):
            lm = lap.get("distance", 0)
            lt = lap.get("moving_time", 0)
            lhr = lap.get("average_heartrate")
            if sport == "Run":
                pace = fmt_pace_run(lm, lt)
                hr_str = f" HR {lhr:.0f}" if lhr else ""
                lap_lines.append(f"#{i} {lm/1000:.2f}km @ {pace}{hr_str}")
            elif is_bike:
                spd = fmt_speed_bike(lm, lt)
                lw = lap.get("average_watts")
                w_str = f" {lw:.0f}W" if lw else ""
                lap_lines.append(f"#{i} {lm/1000:.2f}km @ {spd}{w_str}")
            elif sport == "Swim":
                pace = fmt_pace_swim(lm, lt)
                lap_lines.append(f"#{i} {lm:.0f}m @ {pace}")
        lines.append("  Laps      : " + " | ".join(lap_lines))

    return lines


def display_full(a: dict, streams: dict) -> list[str]:
    """Standard + time-series analysis from streams."""
    lines = display_standard(a)
    sport = a.get("sport_type") or a.get("type", "?")

    hr_s   = streams.get("heartrate", {}).get("data", [])
    time_s = streams.get("time", {}).get("data", [])
    dist_s = streams.get("distance", {}).get("data", [])
    alt_s  = streams.get("altitude", {}).get("data", [])
    vel_s  = streams.get("velocity_smooth", {}).get("data", [])
    watt_s = streams.get("watts", {}).get("data", [])
    lat_s  = streams.get("latlng", {}).get("data", [])
    temp_s = streams.get("temp", {}).get("data", [])

    lines.append("")
    lines.append("  ── Streams ──")

    if sport == "Run":
        zone_line = hr_zone_breakdown(hr_s, time_s, sport="run")
        if zone_line:
            lines.append(zone_line)
        splits = pace_splits_run(dist_s, time_s)
        if splits:
            lines.append(splits)

    if sport == "Ride" and watt_s:
        lines.append(power_stats(watt_s))

    if alt_s:
        lines.append(altitude_profile(alt_s))

    if lat_s:
        lines.append(gps_summary(lat_s))

    if temp_s:
        valid_t = [t for t in temp_s if t is not None]
        if valid_t:
            lines.append(f"  Temp      : {min(valid_t):.0f}°C min / {max(valid_t):.0f}°C max (from device)")

    return lines


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days",   type=int, default=7, help="Days back from now (ignored if --from/--to set)")
    parser.add_argument("--from",   dest="date_from", metavar="YYYY-MM-DD", help="Start date (inclusive)")
    parser.add_argument("--to",     dest="date_to",   metavar="YYYY-MM-DD", help="End date (inclusive, defaults to today)")
    parser.add_argument("--sport",  choices=["run", "bike", "swim"])
    parser.add_argument("--detail", choices=["summary", "standard", "full"], default="standard")
    parser.add_argument("--id",     type=int, help="Fetch a single activity by Strava ID")
    args = parser.parse_args()

    client = StravaClient()
    client.get_access_token()

    # ── Single activity mode ──────────────────────────────────────────────────
    if args.id:
        import requests as req
        detail = args.detail if args.detail != "summary" else "standard"
        a = client.get_activity_details(args.id)
        if detail == "full":
            headers = {"Authorization": f"Bearer {client.access_token}"}
            resp = req.get(f"{client.BASE_URL}/activities/{args.id}/streams",
                           headers=headers,
                           params={"keys": STREAM_TYPES, "key_by_type": "true"})
            streams = resp.json() if resp.ok else {}
            lines = display_full(a, streams)
        else:
            lines = display_standard(a)
        print("\n".join(lines))
        return

    # ── Multi-activity mode ───────────────────────────────────────────────────
    now = datetime.now(timezone.utc)

    if args.date_from:
        after  = int(datetime.fromisoformat(args.date_from).replace(tzinfo=timezone.utc).timestamp())
        end_dt = args.date_to or date.today().isoformat()
        before = int((datetime.fromisoformat(end_dt).replace(tzinfo=timezone.utc) + timedelta(days=1)).timestamp())
        range_label = f"{args.date_from} → {end_dt}"
    else:
        after  = int(now.timestamp()) - args.days * 86400
        before = None
        range_label = f"last {args.days} days"

    raw = client.get_activities(after=after, before=before, per_page=50)
    activities = client.filter_triathlon_activities(raw)

    if args.sport:
        sport_map = {"run": "Run", "bike": "Ride", "swim": "Swim"}
        target = sport_map[args.sport]
        activities = [a for a in activities if (a.get("sport_type") or a.get("type")) == target]

    activities.sort(key=lambda a: a.get("start_date_local", ""))

    if not activities:
        print(f"No triathlon activities found ({range_label}).")
        return

    print(f"\n=== Strava — {range_label} | detail: {args.detail} | {len(activities)} sessions ===\n")

    by_sport = {"Run": [], "Ride": [], "Swim": []}
    for a in activities:
        sport = a.get("sport_type") or a.get("type", "")
        if sport == "VirtualRide":
            sport = "Ride"
        by_sport.get(sport, []).append(a)

    for sport, label in [("Run", "RUNNING"), ("Ride", "CYCLING"), ("Swim", "SWIMMING")]:
        group = by_sport[sport]
        if not group:
            continue
        total_dist = sum(a.get("distance", 0) for a in group)
        total_time = sum(a.get("moving_time", 0) for a in group)
        print(f"── {label} ({len(group)} sessions | {total_dist/1000:.1f} km | {fmt_duration(total_time)}) ──\n")

        for a in group:
            if args.detail == "summary":
                lines = display_summary(a)
            elif args.detail == "standard":
                detail_data = client.get_activity_details(a["id"])
                lines = display_standard(detail_data)
            else:  # full
                detail_data = client.get_activity_details(a["id"])
                url = f"{client.BASE_URL}/activities/{a['id']}/streams"
                headers = {"Authorization": f"Bearer {client.access_token}"}
                import requests as req
                resp = req.get(url, headers=headers,
                               params={"keys": STREAM_TYPES, "key_by_type": "true"})
                streams = resp.json() if resp.ok else {}
                lines = display_full(detail_data, streams)

            print("\n".join(lines))
            print()


if __name__ == "__main__":
    main()
