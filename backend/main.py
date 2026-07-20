"""
Space Situational Awareness — backend
Fetches live TLE (Two-Line Element) data from CelesTrak and propagates
real orbital positions using SGP4 (via skyfield). No ML needed for this
layer — this is Version 2 of the roadmap: a real, live satellite map.

Run:
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000
"""

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from skyfield.api import EarthSatellite, Loader, load, wgs84

from solar_system import MOONS, PLANETS, SUN
from exoplanets import FEATURED_SYSTEMS, get_system, search_hostnames

app = FastAPI(title="SSA Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this in production
    allow_methods=["*"],
    allow_headers=["*"],
)

TS = load.timescale()

# Separate loader/cache dir for the JPL ephemeris (de421.bsp, ~17MB, downloaded
# once on first use and cached here) — needed to know where the Sun is, so we
# can tell whether a satellite is sunlit and whether the sky is dark enough
# to actually see it.
_eph_loader = Loader("./skyfield-data")
_eph_cache = None


def get_ephemeris():
    global _eph_cache
    if _eph_cache is None:
        _eph_cache = _eph_loader("de421.bsp")
    return _eph_cache


COMPASS_POINTS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def azimuth_to_compass(az_deg: float) -> str:
    idx = round(az_deg / 22.5) % 16
    return COMPASS_POINTS[idx]

# CelesTrak TLE groups. "stations" is small (~100) and fast for a demo.
# Swap to "active" for thousands of objects once things work.
GROUPS = {
    # general / active payloads
    "stations": "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    "visual": "https://celestrak.org/NORAD/elements/gp.php?GROUP=visual&FORMAT=tle",
    "active": "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle",
    # constellations
    "starlink": "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle",
    "oneweb": "https://celestrak.org/NORAD/elements/gp.php?GROUP=oneweb&FORMAT=tle",
    "iridium-NEXT": "https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-NEXT&FORMAT=tle",
    "globalstar": "https://celestrak.org/NORAD/elements/gp.php?GROUP=globalstar&FORMAT=tle",
    "orbcomm": "https://celestrak.org/NORAD/elements/gp.php?GROUP=orbcomm&FORMAT=tle",
    "planet": "https://celestrak.org/NORAD/elements/gp.php?GROUP=planet&FORMAT=tle",
    "spire": "https://celestrak.org/NORAD/elements/gp.php?GROUP=spire&FORMAT=tle",
    # navigation / positioning
    "gps-ops": "https://celestrak.org/NORAD/elements/gp.php?GROUP=gps-ops&FORMAT=tle",
    # comms / broadcast
    "intelsat": "https://celestrak.org/NORAD/elements/gp.php?GROUP=intelsat&FORMAT=tle",
    "ses": "https://celestrak.org/NORAD/elements/gp.php?GROUP=ses&FORMAT=tle",
    "geo": "https://celestrak.org/NORAD/elements/gp.php?GROUP=geo&FORMAT=tle",
    "amateur": "https://celestrak.org/NORAD/elements/gp.php?GROUP=amateur&FORMAT=tle",
    "satnogs": "https://celestrak.org/NORAD/elements/gp.php?GROUP=satnogs&FORMAT=tle",
    # earth observation / science
    "weather": "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle",
    "science": "https://celestrak.org/NORAD/elements/gp.php?GROUP=science&FORMAT=tle",
    "cubesat": "https://celestrak.org/NORAD/elements/gp.php?GROUP=cubesat&FORMAT=tle",
    # debris fields — the four most significant trackable LEO debris clouds:
    # Cosmos 1408 (2021 Russian ASAT test), Fengyun-1C (2007 Chinese ASAT
    # test — among the largest debris-generating events ever), and the two
    # sides of the 2009 Iridium 33 / Cosmos 2251 collision.
    "cosmos-1408-debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=cosmos-1408-debris&FORMAT=tle",
    "fengyun-1c-debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=fengyun-1c-debris&FORMAT=tle",
    "iridium-33-debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-33-debris&FORMAT=tle",
    "cosmos-2251-debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=cosmos-2251-debris&FORMAT=tle",
}

# CelesTrak's object names follow a consistent convention that reveals what
# kind of object something actually is — not just "a satellite." Parsing it
# lets any group (not only the dedicated debris groups above) be broken down
# into payload / rocket body / debris / unknown.
def classify_object_type(name: str) -> str:
    n = name.upper()
    if re.search(r"\bDEB\b", n) or "DEBRIS" in n:
        return "Debris"
    if re.search(r"\bR/B\b", n):
        return "Rocket Body"
    return "Payload"

# Simple in-memory cache: {group: (fetched_at_epoch, [EarthSatellite, ...])}
_cache: dict[str, tuple[float, list[EarthSatellite]]] = {}
CACHE_TTL_SECONDS = 60 * 60 * 6  # TLEs are only accurate for ~a day or two anyway


def fetch_satellites(group: str) -> list[EarthSatellite]:
    now = time.time()
    cached = _cache.get(group)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    url = GROUPS.get(group)
    if not url:
        raise HTTPException(status_code=400, detail=f"Unknown group '{group}'")

    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    lines = [l for l in resp.text.splitlines() if l.strip()]

    sats = []
    for i in range(0, len(lines) - 2, 3):
        name, l1, l2 = lines[i].strip(), lines[i + 1], lines[i + 2]
        try:
            sats.append(EarthSatellite(l1, l2, name, TS))
        except Exception:
            continue  # skip malformed entries rather than failing the whole batch

    _cache[group] = (now, sats)
    return sats


def satellite_state(sat: EarthSatellite, t) -> dict:
    geocentric = sat.at(t)
    subpoint = wgs84.subpoint(geocentric)
    velocity_km_s = geocentric.velocity.km_per_s
    speed = (velocity_km_s[0] ** 2 + velocity_km_s[1] ** 2 + velocity_km_s[2] ** 2) ** 0.5
    name = sat.name.strip()

    return {
        "name": name,
        "norad_id": sat.model.satnum,
        "lat": round(subpoint.latitude.degrees, 4),
        "lon": round(subpoint.longitude.degrees, 4),
        "alt_km": round(subpoint.elevation.km, 2),
        "speed_km_s": round(speed, 3),
        "object_type": classify_object_type(name),
    }


@app.get("/api/satellites")
def get_satellites(
    group: str = Query("stations", description="TLE group: stations | visual | active | debris"),
    limit: Optional[int] = Query(None, description="Cap number of objects returned"),
):
    sats = fetch_satellites(group)
    if limit:
        sats = sats[:limit]

    t = TS.from_datetime(datetime.now(timezone.utc))
    results = []
    for sat in sats:
        try:
            results.append(satellite_state(sat, t))
        except Exception:
            continue  # propagation can fail for stale/bad elements; skip rather than 500

    return {
        "group": group,
        "count": len(results),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "satellites": results,
    }


@app.get("/api/satellite/{norad_id}/predict")
def predict_track(norad_id: int, group: str = "stations", minutes_ahead: int = 90, step_minutes: int = 2):
    """Predict a satellite's ground track forward in time (simple propagation, no collision math yet)."""
    sats = fetch_satellites(group)
    sat = next((s for s in sats if s.model.satnum == norad_id), None)
    if not sat:
        raise HTTPException(status_code=404, detail="Satellite not found in this group")

    now = datetime.now(timezone.utc)
    track = []
    for m in range(0, minutes_ahead + 1, step_minutes):
        t = TS.from_datetime(now.replace(microsecond=0) + timedelta(minutes=m))
        state = satellite_state(sat, t)
        state["t_plus_min"] = m
        track.append(state)

    return {"norad_id": norad_id, "name": sat.name.strip(), "track": track}


@app.get("/api/collision-check")
def collision_check(
    group_a: str = Query("active", description="Primary group to screen"),
    group_b: str = Query("cosmos-1408-debris", description="Group to screen group_a against. Same as group_a = within-group screening."),
    limit_a: int = Query(40, description="Cap objects from group_a — pairs grow with n_a * n_b"),
    limit_b: int = Query(40, description="Cap objects from group_b"),
    minutes_ahead: int = Query(180, description="How far forward to screen"),
    step_minutes: int = Query(1, description="Time resolution of the screen"),
    threshold_km: float = Query(5.0, description="Flag pairs whose closest approach is under this distance"),
):
    """
    Simplified conjunction screening between two groups, using real GCRS
    (inertial-frame) position vectors — no need to convert to lat/lon/ECEF
    for a distance check, since both objects are compared in the same
    frame at the same instant.

    Defaults to screening group_a against a *different* group_b on
    purpose: screening a group against itself is misleading for anything
    that's a real formation (a station and its own docked modules,
    a constellation shell flying in coordinated proximity by design,
    debris fragments from one breakup event that share nearly-identical
    orbits) — those will always look like "conjunctions" because they're
    supposed to be close together. Pass group_b == group_a explicitly if
    you do want within-group screening; just expect more noise.

    This is a legitimate first-pass conjunction screen, just at low
    fidelity: real SSA systems use tighter thresholds, finer time steps,
    and propagation error covariance — this is the "simple motion model"
    version the roadmap explicitly says is fine to start with.
    """
    sats_a = fetch_satellites(group_a)[:limit_a]
    same_group = group_a == group_b
    sats_b = sats_a if same_group else fetch_satellites(group_b)[:limit_b]

    if len(sats_a) < 1 or len(sats_b) < 1 or (same_group and len(sats_a) < 2):
        raise HTTPException(status_code=400, detail="Need at least 2 objects to screen")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    offsets = list(range(0, minutes_ahead + 1, step_minutes))
    times = [TS.from_datetime(now + timedelta(minutes=m)) for m in offsets]

    def propagate(sats):
        positions = []
        for sat in sats:
            row = []
            for t in times:
                try:
                    row.append(tuple(sat.at(t).position.km))
                except Exception:
                    row.append(None)
            positions.append(row)
        return positions

    positions_a = propagate(sats_a)
    positions_b = positions_a if same_group else propagate(sats_b)

    conjunctions = []
    n_a, n_b = len(sats_a), len(sats_b)
    for i in range(n_a):
        j_start = i + 1 if same_group else 0
        for j in range(j_start, n_b):
            min_dist = None
            min_k = None
            for k in range(len(times)):
                pi, pj = positions_a[i][k], positions_b[j][k]
                if pi is None or pj is None:
                    continue
                d = ((pi[0] - pj[0]) ** 2 + (pi[1] - pj[1]) ** 2 + (pi[2] - pj[2]) ** 2) ** 0.5
                if min_dist is None or d < min_dist:
                    min_dist, min_k = d, k
            if min_dist is not None and min_dist <= threshold_km:
                t_tca = times[min_k]
                pos_a = satellite_state(sats_a[i], t_tca)
                pos_b = satellite_state(sats_b[j], t_tca)
                conjunctions.append({
                    "object_a": {"name": sats_a[i].name.strip(), "norad_id": sats_a[i].model.satnum,
                                 "lat": pos_a["lat"], "lon": pos_a["lon"], "alt_km": pos_a["alt_km"]},
                    "object_b": {"name": sats_b[j].name.strip(), "norad_id": sats_b[j].model.satnum,
                                 "lat": pos_b["lat"], "lon": pos_b["lon"], "alt_km": pos_b["alt_km"]},
                    "min_distance_km": round(min_dist, 2),
                    "minutes_to_closest_approach": offsets[min_k],
                    "time_of_closest_approach": (now + timedelta(minutes=offsets[min_k])).isoformat(),
                })

    conjunctions.sort(key=lambda c: c["min_distance_km"])

    return {
        "group_a": group_a,
        "group_b": group_b,
        "same_group": same_group,
        "objects_screened_a": n_a,
        "objects_screened_b": n_b,
        "pairs_screened": (n_a * (n_a - 1) // 2) if same_group else (n_a * n_b),
        "threshold_km": threshold_km,
        "window_minutes": minutes_ahead,
        "generated_at": now.isoformat(),
        "conjunctions": conjunctions,
    }


@app.get("/api/passes")
def satellite_passes(
    norad_id: int,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    group: str = Query("stations"),
    hours_ahead: int = Query(72, le=168),
    step_seconds: int = Query(60, ge=15, le=300),
    min_elevation_deg: float = Query(10.0, description="Ignore passes that never climb above this"),
):
    """
    Real overhead-pass prediction for a given satellite from a given
    lat/lon: when it rises above min_elevation_deg, where it peaks, and
    whether it's actually visible to the naked eye (satellite sunlit +
    observer's sky dark enough — this is why satellites are only
    spottable around dawn/dusk, not at noon or in full darkness).
    """
    sats = fetch_satellites(group)
    sat = next((s for s in sats if s.model.satnum == norad_id), None)
    if not sat:
        raise HTTPException(status_code=404, detail="Satellite not found in this group")

    try:
        eph = get_ephemeris()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not load ephemeris (needs internet on first run): {e}")

    earth, sun = eph["earth"], eph["sun"]
    observer = wgs84.latlon(lat, lon)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    n_steps = int(hours_ahead * 3600 / step_seconds)

    passes = []
    in_pass = False
    current = None

    for i in range(n_steps):
        t = TS.from_datetime(now + timedelta(seconds=i * step_seconds))
        alt, az, _ = (sat - observer).at(t).altaz()
        alt_deg = alt.degrees

        if alt_deg >= min_elevation_deg:
            try:
                sunlit = sat.at(t).is_sunlit(eph)
            except Exception:
                sunlit = False
            sun_alt, _, _ = (earth + observer).at(t).observe(sun).apparent().altaz()
            sky_dark = sun_alt.degrees < -6  # civil twilight or darker
            visible_now = bool(sunlit and sky_dark)

            if not in_pass:
                in_pass = True
                current = {
                    "start_utc": t.utc_iso(),
                    "max_elevation_deg": round(alt_deg, 1),
                    "max_elevation_time_utc": t.utc_iso(),
                    "max_azimuth_deg": round(az.degrees, 1),
                    "visible_at_peak": visible_now,
                    "any_step_visible": visible_now,
                }
            else:
                current["any_step_visible"] = current["any_step_visible"] or visible_now
                if alt_deg > current["max_elevation_deg"]:
                    current["max_elevation_deg"] = round(alt_deg, 1)
                    current["max_elevation_time_utc"] = t.utc_iso()
                    current["max_azimuth_deg"] = round(az.degrees, 1)
                    current["visible_at_peak"] = visible_now
        else:
            if in_pass:
                current["end_utc"] = t.utc_iso()
                passes.append(current)
                in_pass = False
                current = None

    if in_pass:
        current["end_utc"] = None  # still above horizon when the prediction window ran out
        passes.append(current)

    for p in passes:
        p["compass"] = azimuth_to_compass(p["max_azimuth_deg"])

    return {
        "norad_id": norad_id,
        "name": sat.name.strip(),
        "observer": {"lat": lat, "lon": lon},
        "min_elevation_deg": min_elevation_deg,
        "window_hours": hours_ahead,
        "generated_at": now.isoformat(),
        "passes": passes,
    }


@app.get("/api/solar-system")
def solar_system():
    """
    Static reference data for the solar system view: Keplerian orbital
    elements (J2000 epoch) for the planets, plus physical facts for
    planets, moons, and the Sun.

    Position propagation happens client-side (a straightforward two-body
    Kepler solve) rather than here — that's what lets the frontend scrub
    or speed up simulated time smoothly without round-tripping to the
    server every animation frame. This endpoint just serves the reference
    tables once; they don't change.
    """
    return {
        "epoch_jd": 2451545.0,  # J2000.0
        "sun": SUN,
        "planets": PLANETS,
        "moons": MOONS,
    }


@app.get("/api/exoplanets/featured")
def exoplanets_featured():
    """A curated list of well-known systems, so a hobbyist has somewhere to start."""
    return {"systems": FEATURED_SYSTEMS}


@app.get("/api/exoplanets/search")
def exoplanets_search(q: str = Query(..., min_length=2), limit: int = Query(15, le=50)):
    try:
        names = search_hostnames(q, limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Exoplanet Archive search failed: {e}")
    return {"query": q, "hostnames": names}


@app.get("/api/exoplanets/system")
def exoplanets_system(hostname: str):
    """
    Real data from NASA's Exoplanet Archive for every confirmed planet
    around a given star, plus a computed Earth Similarity Index and
    habitable-zone status per planet. See exoplanets.py for the ESI
    methodology and its sourcing.
    """
    try:
        data = get_system(hostname)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Exoplanet Archive query failed: {e}")
    if not data["found"]:
        raise HTTPException(status_code=404, detail=f"No confirmed planets found for host '{hostname}'")
    return data


@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Version 3 — additional live data layers. Each of these proxies a real public
# feed so the frontend doesn't have to deal with CORS, and so results get a
# short cache instead of hammering upstream APIs on every poll.
# ---------------------------------------------------------------------------

_generic_cache: dict[str, tuple[float, dict]] = {}


def cached_get(key: str, url: str, ttl: int, **kwargs) -> dict:
    now = time.time()
    hit = _generic_cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    resp = requests.get(url, timeout=10, **kwargs)
    resp.raise_for_status()
    data = resp.json()
    _generic_cache[key] = (now, data)
    return data


@app.get("/api/iss")
def iss_now():
    """Live ISS position (wheretheiss.at) + current crew aboard (open-notify)."""
    result = {"position": None, "crew": None, "error": None}

    try:
        pos = cached_get("iss_pos", "https://api.wheretheiss.at/v1/satellites/25544", ttl=10)
        result["position"] = {
            "lat": pos.get("latitude"),
            "lon": pos.get("longitude"),
            "alt_km": pos.get("altitude"),
            "velocity_kph": pos.get("velocity"),
            "visibility": pos.get("visibility"),
        }
    except Exception as e:
        result["error"] = f"position feed failed: {e}"

    try:
        astros = cached_get("iss_crew", "http://api.open-notify.org/astros.json", ttl=3600)
        iss_crew = [p["name"] for p in astros.get("people", []) if p.get("craft") == "ISS"]
        result["crew"] = {"count": len(iss_crew), "names": iss_crew}
    except Exception as e:
        # crew roster is a nice-to-have; don't let it blank out position data
        result["crew"] = {"count": None, "names": [], "error": str(e)}

    return result


@app.get("/api/launches")
def upcoming_launches(limit: int = Query(6, le=20)):
    """Upcoming rocket launches (Launch Library 2 — thespacedevs.com)."""
    try:
        data = cached_get(
            "launches",
            f"https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit={limit}&mode=normal",
            ttl=900,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"launch feed unavailable: {e}")

    launches = []
    for item in data.get("results", []):
        pad = item.get("pad") or {}
        location = pad.get("location") or {}
        launches.append({
            "name": item.get("name"),
            "net": item.get("net"),  # scheduled launch time, ISO 8601
            "status": (item.get("status") or {}).get("name"),
            "rocket": ((item.get("rocket") or {}).get("configuration") or {}).get("name"),
            "pad_name": pad.get("name"),
            "location_name": location.get("name"),
            "lat": _safe_float(pad.get("latitude")),
            "lon": _safe_float(pad.get("longitude")),
        })
    return {"count": len(launches), "launches": launches}


@app.get("/api/neo")
def near_earth_objects(days: int = Query(7, le=7), api_key: str = Query("DEMO_KEY")):
    """
    Near-Earth object close approaches (NASA NeoWs). DEMO_KEY works but is
    heavily rate-limited (~30/hr) — get a free personal key at api.nasa.gov
    and pass it as ?api_key=... for real use.
    """
    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=min(days, 7))
    try:
        data = cached_get(
            f"neo_{today}_{end}",
            "https://api.nasa.gov/neo/rest/v1/feed",
            ttl=3600,
            params={"start_date": today.isoformat(), "end_date": end.isoformat(), "api_key": api_key},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NEO feed unavailable: {e}")

    objects = []
    for date_key, items in data.get("near_earth_objects", {}).items():
        for obj in items:
            approach = (obj.get("close_approach_data") or [{}])[0]
            diameter = (obj.get("estimated_diameter") or {}).get("kilometers", {})
            objects.append({
                "name": obj.get("name"),
                "date": date_key,
                "hazardous": obj.get("is_potentially_hazardous_asteroid", False),
                "diameter_km_min": diameter.get("estimated_diameter_min"),
                "diameter_km_max": diameter.get("estimated_diameter_max"),
                "miss_distance_km": _safe_float((approach.get("miss_distance") or {}).get("kilometers")),
                "velocity_km_s": _safe_float((approach.get("relative_velocity") or {}).get("kilometers_per_second")),
            })

    objects.sort(key=lambda o: o["miss_distance_km"] if o["miss_distance_km"] is not None else float("inf"))
    return {"count": len(objects), "objects": objects}


@app.get("/api/space-weather")
def space_weather():
    """Latest planetary Kp index (NOAA SWPC) — a standard geomagnetic-activity indicator."""
    try:
        data = cached_get(
            "kp_index",
            "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json",
            ttl=600,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"space weather feed unavailable: {e}")

    if not data:
        raise HTTPException(status_code=502, detail="empty space weather response")

    latest = data[-1]
    kp = _safe_float(latest.get("kp_index", latest.get("kp")))

    if kp is None:
        status = "unknown"
    elif kp < 4:
        status = "quiet"
    elif kp < 6:
        status = "unsettled"
    else:
        status = "storm watch"

    return {"kp_index": kp, "status": status, "time_tag": latest.get("time_tag")}


def _safe_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
