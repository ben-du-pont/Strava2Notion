#!/usr/bin/env python3
"""
fit_reconstructor.py — Extend a partial Garmin FIT run file with synthetic GPS data.

Usage:
    python fit_reconstructor.py <partial.fit> [--output <full.fit>] [--estimated-km N]
"""

import argparse
import io
import json
import math
import threading
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import fitparse
import numpy as np
import requests
from garmin_fit_sdk import Decoder, Encoder, Stream
from scipy.interpolate import CubicSpline, interp1d
from scipy.ndimage import gaussian_filter1d
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SC_PER_DEG = 2**31 / 180
DEG_PER_SC = 180 / 2**31
METERS_PER_DEG_LAT = 111319.5
FIT_EPOCH_S = 631065600  # seconds from Unix epoch to FIT epoch (1989-12-31)

# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — Load FIT file
# ─────────────────────────────────────────────────────────────────────────────

def load_fit(fit_path: str) -> tuple[list[dict], dict]:
    """Read all messages from a FIT file using the Decoder.

    Returns:
        records: list of record dicts (mesg_num=20), timestamps as datetime objects
        summary: dict mapping mesg_num → list of message dicts for all other messages
    """
    records: list[dict] = []
    summary: dict[int, list[dict]] = {}

    def on_mesg(mesg_num: int, mesg: dict) -> None:
        if mesg_num == 20:
            records.append(dict(mesg))
        else:
            summary.setdefault(mesg_num, []).append(dict(mesg))

    stream = Stream.from_file(fit_path)
    Decoder(stream).read(mesg_listener=on_mesg)
    return records, summary


def sc_to_deg(sc: int) -> float:
    return sc * DEG_PER_SC


def deg_to_sc(deg: float) -> int:
    return int(deg * SC_PER_DEG)


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Interactive browser map
# ─────────────────────────────────────────────────────────────────────────────

_MAP_HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>Run Reconstructor</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, sans-serif; background: #111; color: #eee; display: flex; flex-direction: column; height: 100vh; }
#toolbar { display: flex; align-items: center; gap: 12px; padding: 10px 16px; background: #1a1a2e; border-bottom: 1px solid #333; flex-shrink: 0; }
#toolbar h1 { font-size: 15px; font-weight: 600; color: #7eb8f7; white-space: nowrap; }
#status { flex: 1; font-size: 13px; color: #aaa; }
button { padding: 7px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500; }
#btn-undo { background: #333; color: #ccc; }
#btn-undo:hover:not(:disabled) { background: #444; }
#btn-generate { background: #0096c7; color: #fff; }
#btn-generate:hover:not(:disabled) { background: #00b4d8; }
button:disabled { opacity: 0.35; cursor: not-allowed; }
#map { flex: 1; }
#coords { position: fixed; bottom: 8px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.65); color: #ddd; font-size: 11px; padding: 3px 10px; border-radius: 10px; pointer-events: none; z-index: 1000; }
</style>
</head>
<body>
<div id="toolbar">
  <h1>Run Reconstructor</h1>
  <div id="status">Click the map to place waypoints along your continued route</div>
  <button id="btn-undo" onclick="undoLast()" disabled>Undo</button>
  <button id="btn-generate" onclick="generate()" disabled>Generate FIT &#8250;</button>
</div>
<div id="map"></div>
<div id="coords"></div>
<script>
const track = TRACK_JSON;
const waypoints = [];
const markers = [];
let waypointLine = null;

const map = L.map('map', { zoomControl: true });
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors', maxZoom: 19
}).addTo(map);

const poly = L.polyline(track, { color: '#2196F3', weight: 5, opacity: 0.85 }).addTo(map);
map.fitBounds(poly.getBounds().pad(0.25));

const lastPt = track[track.length - 1];
const starIcon = L.divIcon({
  html: '<div style="background:#FF5722;color:white;border-radius:50%;width:22px;height:22px;display:flex;align-items:center;justify-content:center;font-size:15px;line-height:22px;font-weight:bold;box-shadow:0 2px 4px rgba(0,0,0,0.4)">&#9733;</div>',
  iconSize: [22, 22], iconAnchor: [11, 11], className: ''
});
L.marker(lastPt, { icon: starIcon }).addTo(map).bindTooltip('Watch turned off here', { permanent: false });

map.on('mousemove', e => {
  document.getElementById('coords').textContent =
    e.latlng.lat.toFixed(6) + ', ' + e.latlng.lng.toFixed(6);
});

map.on('click', e => {
  const idx = waypoints.length + 1;
  const wp = { lat: e.latlng.lat, lon: e.latlng.lng };
  waypoints.push(wp);
  const icon = L.divIcon({
    html: `<div style="background:#E91E63;color:white;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:bold;box-shadow:0 2px 4px rgba(0,0,0,0.4)">${idx}</div>`,
    iconSize: [24, 24], iconAnchor: [12, 12], className: ''
  });
  markers.push(L.marker(e.latlng, { icon }).addTo(map));
  redrawLine();
  updateUI();
});

function redrawLine() {
  if (waypointLine) map.removeLayer(waypointLine);
  if (waypoints.length > 0) {
    const pts = [lastPt, ...waypoints.map(w => [w.lat, w.lon])];
    waypointLine = L.polyline(pts, {
      color: '#E91E63', weight: 4, dashArray: '10 7', opacity: 0.9
    }).addTo(map);
  }
}

function undoLast() {
  if (!waypoints.length) return;
  waypoints.pop();
  map.removeLayer(markers.pop());
  redrawLine();
  updateUI();
}

function updateUI() {
  const n = waypoints.length;
  document.getElementById('status').textContent = n === 0
    ? 'Click the map to place waypoints along your continued route'
    : n + ' waypoint' + (n > 1 ? 's' : '') + ' placed — add more or click Generate FIT';
  document.getElementById('btn-undo').disabled = n === 0;
  document.getElementById('btn-generate').disabled = n === 0;
}

function generate() {
  document.getElementById('btn-generate').disabled = true;
  document.getElementById('btn-undo').disabled = true;
  document.getElementById('status').textContent = 'Sending to Python… check your terminal.';
  fetch('/waypoints', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(waypoints)
  }).then(r => {
    document.getElementById('status').textContent = r.ok
      ? '✓ Done! Check your terminal for the output file path.'
      : '✗ Error — see terminal.';
  }).catch(() => {
    document.getElementById('status').textContent = '✗ Could not reach Python server.';
  });
}
</script>
</body>
</html>"""


class _MapHandler(BaseHTTPRequestHandler):
    waypoints: list[dict] = []
    done_event: threading.Event = threading.Event()
    track_json: str = "[]"

    def do_GET(self) -> None:
        html = _MapHandler.track_json  # filled before server starts
        page = _MAP_HTML.replace("TRACK_JSON", _MapHandler.track_json)
        body = page.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _MapHandler.waypoints = json.loads(body)
        self.send_response(200)
        self.end_headers()
        _MapHandler.done_event.set()

    def log_message(self, *args) -> None:
        pass


def collect_waypoints(records: list[dict]) -> list[dict]:
    """Serve an interactive map in the browser; return user-placed waypoints."""
    # Downsample track to keep page size small (every 5th point)
    track = [
        [sc_to_deg(r["position_lat"]), sc_to_deg(r["position_long"])]
        for r in records[::5]
        if r.get("position_lat") is not None and r.get("position_long") is not None
    ]
    _MapHandler.track_json = json.dumps(track)
    _MapHandler.done_event.clear()
    _MapHandler.waypoints = []

    server = HTTPServer(("localhost", 8765), _MapHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print("\nOpening map at http://localhost:8765 ...")
    print("Place waypoints along your route, then click 'Generate FIT'.\n")
    time.sleep(0.4)
    webbrowser.open("http://localhost:8765")
    _MapHandler.done_event.wait()
    server.shutdown()

    pts = _MapHandler.waypoints
    print(f"  Received {len(pts)} waypoint{'s' if len(pts) != 1 else ''}.")
    return pts


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — GPS path interpolation
# ─────────────────────────────────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two lat/lon points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(a, 1.0)))


def build_gps_splines(
    waypoints_latlon: list[tuple[float, float]],
) -> tuple:
    """
    Fit CubicSpline to a waypoint list, re-parameterised by arc length.

    Returns:
        arc_to_lat: callable(arc_m) -> latitude degrees
        arc_to_lon: callable(arc_m) -> longitude degrees
        total_arc_m: float, total path length in metres
    """
    lats = np.array([p[0] for p in waypoints_latlon])
    lons = np.array([p[1] for p in waypoints_latlon])
    n = len(lats)

    # Chord-length parameterisation
    t = np.zeros(n)
    for i in range(1, n):
        t[i] = t[i - 1] + haversine(lats[i - 1], lons[i - 1], lats[i], lons[i])

    if n == 2:
        # Degenerate case: straight line
        total_arc_m = t[-1]
        arc_to_lat = interp1d(t, lats, kind="linear", fill_value="extrapolate")
        arc_to_lon = interp1d(t, lons, kind="linear", fill_value="extrapolate")
        return arc_to_lat, arc_to_lon, float(total_arc_m)

    cs_lat = CubicSpline(t, lats, bc_type="not-a-knot")
    cs_lon = CubicSpline(t, lons, bc_type="not-a-knot")

    # Arc-length reparameterisation
    N_FINE = 10_000
    t_fine = np.linspace(t[0], t[-1], N_FINE)
    lat_fine = cs_lat(t_fine)
    lon_fine = cs_lon(t_fine)

    arc = np.zeros(N_FINE)
    for i in range(1, N_FINE):
        arc[i] = arc[i - 1] + haversine(lat_fine[i - 1], lon_fine[i - 1], lat_fine[i], lon_fine[i])

    total_arc_m = float(arc[-1])
    arc_to_t_fn = interp1d(arc, t_fine, kind="linear", fill_value="extrapolate")

    def arc_to_lat(s: np.ndarray) -> np.ndarray:
        return cs_lat(arc_to_t_fn(np.asarray(s, dtype=float)))

    def arc_to_lon(s: np.ndarray) -> np.ndarray:
        return cs_lon(arc_to_t_fn(np.asarray(s, dtype=float)))

    return arc_to_lat, arc_to_lon, total_arc_m


def ar1_noise(n: int, phi: float, sigma: float, rng: np.random.Generator) -> np.ndarray:
    """AR(1) correlated noise process."""
    out = np.zeros(n)
    for i in range(1, n):
        out[i] = phi * out[i - 1] + rng.normal(0.0, sigma)
    return out


def add_gps_noise(
    lats: np.ndarray,
    lons: np.ndarray,
    rng: np.random.Generator,
    sigma_perp: float = 1.2,
    phi: float = 0.75,
) -> tuple[np.ndarray, np.ndarray]:
    """Add AR(1) noise perpendicular to the path direction (simulates GPS jitter)."""
    n = len(lats)
    perp_m = ar1_noise(n, phi, sigma_perp, rng)

    lats_out = lats.copy()
    lons_out = lons.copy()

    for i in range(n):
        j = i + 1 if i < n - 1 else i - 1
        dlat = lats[j] - lats[i] if i < n - 1 else lats[i] - lats[i - 1]
        dlon = lons[j] - lons[i] if i < n - 1 else lons[i] - lons[i - 1]
        seg = math.sqrt(dlat ** 2 + dlon ** 2)
        if seg < 1e-12:
            continue
        # Rotate 90° to get perpendicular direction
        plat, plon = -dlon / seg, dlat / seg
        m_lat = METERS_PER_DEG_LAT
        m_lon = METERS_PER_DEG_LAT * math.cos(math.radians(float(lats[i])))
        lats_out[i] += perp_m[i] * plat / m_lat
        lons_out[i] += perp_m[i] * plon / m_lon

    return lats_out, lons_out


# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — Elevation from OpenTopoData
# ─────────────────────────────────────────────────────────────────────────────

def fetch_elevations(lat_lon_pairs: list[tuple[float, float]]) -> list[float | None]:
    """Fetch SRTM30m elevation for each (lat, lon) pair via opentopodata.org."""
    results: list[float | None] = [None] * len(lat_lon_pairs)
    BATCH = 100

    for start in range(0, len(lat_lon_pairs), BATCH):
        batch = lat_lon_pairs[start : start + BATCH]
        locations = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in batch)
        try:
            r = requests.get(
                "https://api.opentopodata.org/v1/srtm30m",
                params={"locations": locations},
                timeout=15,
            )
            if r.status_code == 200:
                for i, entry in enumerate(r.json().get("results", [])):
                    results[start + i] = entry.get("elevation")
            else:
                print(f"  Elevation API returned {r.status_code} for batch {start}.")
        except Exception as exc:
            print(f"  Elevation fetch failed (batch {start}): {exc}")
        if start + BATCH < len(lat_lon_pairs):
            time.sleep(1.1)

    return results


def build_elevation_profile(
    arc_to_lat,
    arc_to_lon,
    total_arc_m: float,
    fallback_alt: float,
    rng: np.random.Generator,
) -> interp1d:
    """Sample elevations along the path, add barometric noise, return interpolator."""
    n_samples = min(100, max(5, int(total_arc_m / 50)))
    sample_arcs = np.linspace(0, total_arc_m, n_samples)
    slats = arc_to_lat(sample_arcs)
    slons = arc_to_lon(sample_arcs)

    raw_elevs = fetch_elevations(list(zip(slats.tolist(), slons.tolist())))
    elev = np.array([e if e is not None else float("nan") for e in raw_elevs])

    # Fill NaNs by linear interpolation between valid samples
    nan_mask = np.isnan(elev)
    if nan_mask.all():
        elev[:] = fallback_alt
    elif nan_mask.any():
        x = np.arange(len(elev))
        elev[nan_mask] = np.interp(x[nan_mask], x[~nan_mask], elev[~nan_mask])

    # Barometric sensor noise: AR(1) σ=0.3m (matches Apple Watch behaviour)
    elev += ar1_noise(n_samples, phi=0.95, sigma=0.3, rng=rng)

    return interp1d(sample_arcs, elev, kind="linear", fill_value="extrapolate")


# ─────────────────────────────────────────────────────────────────────────────
# Section 5 — Regression models
# ─────────────────────────────────────────────────────────────────────────────

def _feature_matrix(
    elapsed: np.ndarray,
    distances: np.ndarray,
    altitudes: np.ndarray,
) -> np.ndarray:
    """Build shared feature matrix from time, distance, and altitude arrays."""
    alt_delta = np.diff(altitudes, prepend=altitudes[0])
    period = 600.0
    return np.column_stack([
        elapsed,
        elapsed ** 2,
        distances,
        altitudes,
        alt_delta,
        np.sin(2 * np.pi * elapsed / period),
        np.cos(2 * np.pi * elapsed / period),
    ])


def train_models(records: list[dict]) -> dict:
    """Fit Ridge regression models for speed, heart_rate, and cadence."""
    n = len(records)
    elapsed = np.arange(n, dtype=float)
    distances = np.array([r.get("distance") or 0.0 for r in records])
    altitudes = np.array([
        r.get("enhanced_altitude") or r.get("altitude") or 430.0 for r in records
    ])
    X = _feature_matrix(elapsed, distances, altitudes)

    models: dict = {}
    for field, clamp in [
        ("enhanced_speed", (2.0, 5.5)),
        ("heart_rate", (90, 200)),
        ("cadence", (70, 120)),
    ]:
        y = np.array([r.get(field) or 0.0 for r in records])
        valid = y > 0
        if valid.sum() < 10:
            models[field] = None
            continue
        pipe = Pipeline([
            ("poly", PolynomialFeatures(degree=2, include_bias=False)),
            ("scale", StandardScaler()),
            ("ridge", Ridge(alpha=1.0)),
        ])
        pipe.fit(X[valid], y[valid])
        models[field] = (pipe, clamp)
        score = pipe.score(X[valid], y[valid])
        print(f"  {field}: R²={score:.3f}")

    return models


def extrapolate_physiology(
    models: dict,
    n_orig: int,
    n_ext: int,
    orig_last_dist: float,
    ext_altitudes: np.ndarray,
    rng: np.random.Generator,
    anchor_hr: float = 160.0,
    max_hr: int = 165,
) -> dict[str, np.ndarray]:
    """Generate synthetic physiology for the extended portion."""
    elapsed = np.arange(n_orig, n_orig + n_ext, dtype=float)
    # Placeholder distances; will be recomputed after speed rescaling
    distances = np.linspace(orig_last_dist, orig_last_dist + 2000, n_ext)
    X = _feature_matrix(elapsed, distances, ext_altitudes)

    result: dict[str, np.ndarray] = {}

    # Speed
    if models.get("enhanced_speed"):
        pipe, (lo, hi) = models["enhanced_speed"]
        trend = pipe.predict(X)
        noise = ar1_noise(n_ext, phi=0.8, sigma=0.12, rng=rng)
        result["enhanced_speed"] = np.clip(trend + noise, lo, hi)
    else:
        result["enhanced_speed"] = np.full(n_ext, 3.0)

    # Heart rate: mean-reverting AR1 anchored at last known value, not regression trend.
    # The regression extrapolates the upward curve from training data which overshoots.
    noise = gaussian_filter1d(ar1_noise(n_ext, phi=0.92, sigma=2.5, rng=rng), sigma=10)
    result["heart_rate"] = np.clip(anchor_hr + noise, 90, max_hr).round().astype(int)

    # Cadence
    if models.get("cadence"):
        pipe, (lo, hi) = models["cadence"]
        trend = pipe.predict(X)
        noise = ar1_noise(n_ext, phi=0.85, sigma=2.5, rng=rng)
        result["cadence"] = np.clip(trend + noise, lo, hi).round().astype(int)
    else:
        result["cadence"] = np.full(n_ext, 90, dtype=int)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Section 6 — Write FIT file
# ─────────────────────────────────────────────────────────────────────────────

def _recompute_summary(
    orig_mesg: dict,
    all_records: list[dict],
    new_end_ts: datetime,
    total_time_s: float,
    total_dist_m: float,
) -> dict:
    """Update a session or lap summary dict with recomputed statistics."""
    hr_vals = [r["heart_rate"] for r in all_records if r.get("heart_rate")]
    cad_vals = [r["cadence"] for r in all_records if r.get("cadence")]
    speed_vals = [
        r.get("enhanced_speed") or r.get("speed") or 0.0 for r in all_records
    ]
    alt_vals = [
        r.get("enhanced_altitude") or r.get("altitude") or 0.0 for r in all_records
    ]

    avg_speed = total_dist_m / total_time_s if total_time_s > 0 else 0.0
    max_speed = float(max(speed_vals)) if speed_vals else 0.0
    avg_hr = int(round(float(np.mean(hr_vals)))) if hr_vals else 0
    max_hr = int(max(hr_vals)) if hr_vals else 0
    min_hr = int(min(hr_vals)) if hr_vals else 0
    avg_cad = int(round(float(np.mean(cad_vals)))) if cad_vals else 0
    max_cad = int(max(cad_vals)) if cad_vals else 0
    max_alt = max(alt_vals) if alt_vals else 0.0
    min_alt = min(alt_vals) if alt_vals else 0.0

    # Cumulative ascent = sum of positive altitude increments
    alt_arr = np.array(alt_vals)
    ascent = int(np.sum(np.diff(alt_arr)[np.diff(alt_arr) > 0])) if len(alt_arr) > 1 else 0

    orig_time = orig_mesg.get("total_timer_time") or total_time_s
    orig_cal = orig_mesg.get("total_calories") or 680
    calories = int(orig_cal * total_time_s / orig_time)

    updated = dict(orig_mesg)
    updated.update({
        "timestamp": new_end_ts,
        "total_timer_time": total_time_s,
        "total_elapsed_time": total_time_s,
        "total_distance": total_dist_m,
        "avg_speed": avg_speed,
        "enhanced_avg_speed": avg_speed,
        "max_speed": max_speed,
        "enhanced_max_speed": max_speed,
        "total_ascent": ascent,
        "total_calories": calories,
        "avg_heart_rate": avg_hr,
        "max_heart_rate": max_hr,
        "min_heart_rate": min_hr,
        "avg_cadence": avg_cad,
        "avg_running_cadence": avg_cad,
        "max_cadence": max_cad,
        "max_running_cadence": max_cad,
        "max_altitude": max_alt,
        "enhanced_max_altitude": max_alt,
        "min_altitude": min_alt,
        "enhanced_min_altitude": min_alt,
    })
    return updated


def write_fit(
    orig_records: list[dict],
    ext_records: list[dict],
    summary: dict[int, list[dict]],
    output_path: str,
) -> None:
    """Encode and write a complete FIT file with original + extended records."""
    all_records = orig_records + ext_records
    new_end_ts = ext_records[-1]["timestamp"] if ext_records else orig_records[-1]["timestamp"]
    total_dist_m = ext_records[-1]["distance"] if ext_records else orig_records[-1].get("distance", 0.0)
    orig_sess = summary.get(18, [{}])[0]
    orig_time = orig_sess.get("total_timer_time") or 0.0
    extra_time = len(ext_records)
    total_time_s = float(orig_time) + extra_time

    enc = Encoder()

    # file_id (mesg_num=0)
    for mesg in summary.get(0, []):
        enc.on_mesg(0, mesg)

    # device_info (mesg_num=23)
    for mesg in summary.get(23, []):
        enc.on_mesg(23, mesg)

    # event: timer start (mesg_num=21, first one)
    events = summary.get(21, [])
    if events:
        enc.on_mesg(21, events[0])

    # Records
    for rec in orig_records:
        enc.on_mesg(20, rec)
    for rec in ext_records:
        enc.on_mesg(20, rec)

    # event: timer stop_all (last event)
    if len(events) > 1:
        stop_evt = dict(events[-1])
        stop_evt["timestamp"] = new_end_ts
        enc.on_mesg(21, stop_evt)

    # lap (mesg_num=19)
    orig_lap = summary.get(19, [{}])[0]
    new_lap = _recompute_summary(orig_lap, all_records, new_end_ts, total_time_s, total_dist_m)
    if ext_records:
        new_lap["end_position_lat"] = ext_records[-1].get("position_lat")
        new_lap["end_position_long"] = ext_records[-1].get("position_long")
    enc.on_mesg(19, new_lap)

    # session (mesg_num=18)
    new_sess = _recompute_summary(orig_sess, all_records, new_end_ts, total_time_s, total_dist_m)
    enc.on_mesg(18, new_sess)

    # activity (mesg_num=34)
    for mesg in summary.get(34, []):
        act = dict(mesg)
        act["timestamp"] = new_end_ts
        act["total_timer_time"] = total_time_s
        # Correct local_timestamp for UTC+2 (Switzerland, May)
        fit_ts = int(new_end_ts.timestamp()) - FIT_EPOCH_S
        act["local_timestamp"] = fit_ts + 7200
        enc.on_mesg(34, act)

    data = enc.close()
    Path(output_path).write_bytes(data)
    print(f"  Written: {output_path} ({len(data):,} bytes)")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def extract_waypoints_from_fit(
    full_fit_path: str,
    orig_end_ts: datetime,
    n_waypoints: int = 20,
) -> list[dict]:
    """Pull GPS waypoints from the extended portion of a previously generated FIT file."""
    ext_records, _ = load_fit(full_fit_path)
    extended = [
        r for r in ext_records
        if r["timestamp"] > orig_end_ts and r.get("position_lat") is not None
    ]
    if not extended:
        raise ValueError(f"No extended records found after {orig_end_ts} in {full_fit_path}")
    step = max(1, len(extended) // n_waypoints)
    sampled = extended[::step]
    if extended[-1] not in sampled:
        sampled.append(extended[-1])
    return [{"lat": sc_to_deg(r["position_lat"]), "lon": sc_to_deg(r["position_long"])} for r in sampled]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extend a partial Garmin FIT run file with synthetic GPS data"
    )
    parser.add_argument("fit_file", help="Path to the partial .fit file")
    parser.add_argument("--output", default=None, help="Output .fit path (default: <name>_full.fit)")
    parser.add_argument("--from-fit", default=None, metavar="PREV_FIT",
                        help="Reuse the GPS route from a previously generated full FIT file (skips the map)")
    parser.add_argument("--estimated-km", type=float, default=None,
                        help="Expected total run distance in km (used for validation only)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    output_path = args.output or (Path(args.fit_file).stem + "_full.fit")
    rng = np.random.default_rng(args.seed)

    # ── 1. Load ──────────────────────────────────────────────────────────────
    print(f"\nLoading {args.fit_file}...")
    records, summary = load_fit(args.fit_file)
    print(f"  {len(records)} records | "
          f"{records[-1].get('distance', 0.0) / 1000:.2f} km | "
          f"{records[0]['timestamp'].strftime('%H:%M')} → {records[-1]['timestamp'].strftime('%H:%M')}")

    last_rec = records[-1]
    anchor_lat = sc_to_deg(last_rec["position_lat"])
    anchor_lon = sc_to_deg(last_rec["position_long"])
    anchor_dist = float(last_rec.get("distance") or 0.0)
    max_ts: datetime = max(r["timestamp"] for r in records)
    fallback_alt = float(last_rec.get("enhanced_altitude") or last_rec.get("altitude") or 430.0)

    # ── 2. Waypoints — interactive map or reuse a previous output ────────────
    if args.from_fit:
        print(f"\nReusing GPS route from {args.from_fit}...")
        waypoints_raw = extract_waypoints_from_fit(args.from_fit, max_ts)
        print(f"  Extracted {len(waypoints_raw)} waypoints.")
    else:
        waypoints_raw = collect_waypoints(records)
        if not waypoints_raw:
            print("No waypoints provided — exiting.")
            return

    # ── 3. Build GPS splines ─────────────────────────────────────────────────
    print("\nBuilding GPS path...")
    all_pts = [(anchor_lat, anchor_lon)] + [(w["lat"], w["lon"]) for w in waypoints_raw]
    arc_to_lat, arc_to_lon, total_arc_m = build_gps_splines(all_pts)
    total_projected_km = (anchor_dist + total_arc_m) / 1000
    print(f"  Extension: {total_arc_m / 1000:.2f} km → projected total: {total_projected_km:.2f} km")

    if args.estimated_km and abs(total_projected_km - args.estimated_km) > 2.0:
        print(f"  WARNING: projected {total_projected_km:.1f} km vs estimated {args.estimated_km:.1f} km "
              f"(>{abs(total_projected_km - args.estimated_km):.1f} km discrepancy).")

    # Number of seconds to generate: based on average pace of last 2 minutes
    last_n = min(120, len(records))
    last_speed = float(np.mean([
        r.get("enhanced_speed") or r.get("speed") or 3.0 for r in records[-last_n:]
    ]))
    n_ext = max(60, int(total_arc_m / last_speed))
    print(f"  Generating {n_ext}s ({n_ext // 60}m {n_ext % 60:02d}s) "
          f"at ~{last_speed:.2f} m/s ({60 / last_speed / 60:.1f} min/km)")

    # ── 4. Elevation ─────────────────────────────────────────────────────────
    print("\nFetching elevation data...")
    elev_fn = build_elevation_profile(arc_to_lat, arc_to_lon, total_arc_m, fallback_alt, rng)

    # ── 5. Train models ──────────────────────────────────────────────────────
    print("\nTraining regression models...")
    models = train_models(records)

    # Generate speed series using placeholder altitudes, then rescale to match arc length
    ext_sample_arcs = np.linspace(0, total_arc_m, n_ext)
    ext_altitudes = elev_fn(ext_sample_arcs)
    last_30s_hr = float(np.mean([
        r.get("heart_rate") or 0 for r in records[-30:] if r.get("heart_rate")
    ]))
    phys = extrapolate_physiology(
        models, len(records), n_ext, anchor_dist, ext_altitudes, rng,
        anchor_hr=last_30s_hr, max_hr=165,
    )

    # Rescale speed so cumulative displacement == total_arc_m
    raw_total = float(np.sum(phys["enhanced_speed"]))
    if raw_total > 0:
        phys["enhanced_speed"] *= total_arc_m / raw_total

    # Cumulative arc positions for GPS sampling
    cum_arc = np.clip(np.cumsum(phys["enhanced_speed"]), 0, total_arc_m)

    # ── 6. Generate GPS + assemble extended records ──────────────────────────
    print("\nGenerating GPS track...")
    ext_lats = arc_to_lat(cum_arc)
    ext_lons = arc_to_lon(cum_arc)
    ext_lats, ext_lons = add_gps_noise(ext_lats, ext_lons, rng)

    ext_records: list[dict] = []
    cumulative_dist = anchor_dist
    for i in range(n_ext):
        cumulative_dist += float(phys["enhanced_speed"][i])
        ts = max_ts + timedelta(seconds=i + 1)
        ext_records.append({
            "timestamp": ts,
            "position_lat": deg_to_sc(float(ext_lats[i])),
            "position_long": deg_to_sc(float(ext_lons[i])),
            "distance": cumulative_dist,
            "enhanced_speed": float(phys["enhanced_speed"][i]),
            "speed": float(phys["enhanced_speed"][i]),
            "enhanced_altitude": float(ext_altitudes[i]),
            "altitude": float(ext_altitudes[i]),
            "heart_rate": int(phys["heart_rate"][i]),
            "cadence": int(phys["cadence"][i]),
        })

    # ── 7. Write FIT ─────────────────────────────────────────────────────────
    print("\nWriting FIT file...")
    write_fit(records, ext_records, summary, output_path)

    # ── Summary ──────────────────────────────────────────────────────────────
    total_dist_km = ext_records[-1]["distance"] / 1000
    total_secs = len(records) + n_ext
    pace_min_km = (total_secs / 60) / total_dist_km if total_dist_km > 0 else 0
    avg_hr_ext = int(np.mean(phys["heart_rate"]))

    print(f"\n{'─' * 50}")
    print(f"  Total distance : {total_dist_km:.2f} km")
    print(f"  Total time     : {total_secs // 60}m {total_secs % 60:02d}s")
    print(f"  Avg pace       : {int(pace_min_km)}:{int((pace_min_km % 1) * 60):02d} /km")
    print(f"  Avg HR (ext)   : {avg_hr_ext} bpm")
    print(f"  Output         : {output_path}")
    print(f"{'─' * 50}")
    print(f"\nUpload {output_path!r} to Strava to record your full run.")


if __name__ == "__main__":
    main()
