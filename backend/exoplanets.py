"""
Exoplanet data via NASA's Exoplanet Archive TAP service (real, live,
public — https://exoplanetarchive.ipac.caltech.edu/TAP/sync). No API key
needed.

Habitability scoring uses the Earth Similarity Index (ESI), a real,
published method (Schulze-Makuch et al. 2011) — not a custom formula,
since the original project's exact methodology wasn't recoverable. ESI
combines radius, density, escape velocity, and equilibrium temperature
into a 0-1 score via weighted geometric means, each normalized against
Earth's own values. Swapping in a different formula later just means
replacing `compute_esi()` — nothing else downstream needs to change.
"""

from typing import Optional

import requests

TAP_BASE = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"

EARTH_MEAN_SURFACE_TEMP_K = 288.0

# A handful of well-known, genuinely interesting systems to offer as
# quick-start options rather than making a hobbyist guess a hostname cold.
FEATURED_SYSTEMS = [
    "TRAPPIST-1", "Kepler-186", "Kepler-442", "Proxima Cen",
    "TOI-700", "Kepler-62", "HD 40307", "GJ 667 C",
]


def _tap_query(adql: str, fmt: str = "json") -> list:
    resp = requests.get(
        TAP_BASE, params={"query": adql, "format": fmt}, timeout=20,
        headers={"User-Agent": "ssa-dashboard/1.0 (https://github.com/; personal project)"},
    )
    resp.raise_for_status()
    return resp.json()


def search_hostnames(q: str, limit: int = 15) -> list:
    """Distinct star (host) names matching a search substring."""
    q_escaped = q.replace("'", "''")
    adql = (
        f"select distinct hostname from ps "
        f"where hostname like '%{q_escaped}%' "
        f"order by hostname asc"
    )
    rows = _tap_query(adql)
    return [r["hostname"] for r in rows[:limit]]


def esi_component(x: float, x_ref: float, weight: float) -> float:
    return (1 - abs((x - x_ref) / (x + x_ref))) ** weight


def compute_esi(radius_earth: Optional[float], mass_earth: Optional[float], eq_temp_k: Optional[float]) -> Optional[float]:
    if not radius_earth or not mass_earth or radius_earth <= 0 or mass_earth <= 0:
        return None

    density_rel = mass_earth / (radius_earth ** 3)          # relative to Earth = 1
    esc_vel_rel = (mass_earth / radius_earth) ** 0.5          # relative to Earth = 1

    esi_radius = esi_component(radius_earth, 1.0, 0.57)
    esi_density = esi_component(density_rel, 1.0, 1.07)
    esi_interior = (esi_radius * esi_density) ** 0.5

    esi_escvel = esi_component(esc_vel_rel, 1.0, 0.70)
    if eq_temp_k and eq_temp_k > 0:
        esi_temp = esi_component(eq_temp_k, EARTH_MEAN_SURFACE_TEMP_K, 5.58)
        esi_surface = (esi_escvel * esi_temp) ** 0.5
    else:
        esi_surface = esi_escvel  # no temperature data — degrade gracefully rather than failing

    return round((esi_interior * esi_surface) ** 0.5, 3)


def habitable_zone_au(st_teff: Optional[float], st_rad: Optional[float]) -> Optional[dict]:
    """
    Conservative habitable zone bounds in AU, from a standard simplified
    formula: stellar luminosity relative to the Sun via L = R^2 * (T/T_sun)^4,
    then inner/outer HZ edges via L^0.5 scaled by empirical solar-flux
    boundaries. This is the textbook simplified version, not a full
    Kopparapu et al. climate-model calculation — good for a visualization,
    not a research claim.
    """
    if not st_teff or not st_rad or st_teff <= 0 or st_rad <= 0:
        return None
    T_sun = 5772.0
    luminosity = (st_rad ** 2) * ((st_teff / T_sun) ** 4)
    inner_au = (luminosity / 1.1) ** 0.5
    outer_au = (luminosity / 0.53) ** 0.5
    return {"inner_au": round(inner_au, 4), "outer_au": round(outer_au, 4)}


def classify_planet_type(radius_earth: Optional[float], mass_earth: Optional[float]) -> str:
    """
    NASA's own public exoplanet catalog (science.nasa.gov/exoplanets/exoplanet-catalog)
    sorts every confirmed planet into one of these four categories — this
    reproduces that same scheme (standard radius thresholds used across
    NASA's popular-science exoplanet materials), falling back to a rough
    mass-based estimate when radius isn't measured.
    """
    if radius_earth:
        if radius_earth < 1.25:
            return "Terrestrial"
        if radius_earth < 2.0:
            return "Super Earth"
        if radius_earth < 6.0:
            return "Neptune-like"
        return "Gas Giant"
    if mass_earth:
        if mass_earth < 2:
            return "Terrestrial"
        if mass_earth < 10:
            return "Super Earth"
        if mass_earth < 50:
            return "Neptune-like"
        return "Gas Giant"
    return "Unknown"


def estimate_eq_temp_k(star_teff: Optional[float], star_radius_solar: Optional[float], a_au: Optional[float]) -> Optional[float]:
    """
    Zero-albedo equilibrium temperature estimate: T = T_star * sqrt(R_star / (2a)),
    a standard, real formula — used only when the Archive's own directly-measured
    pl_eqt is missing (common; many planets, especially radial-velocity detections,
    don't have a reported equilibrium temperature). Verified against Earth before
    shipping: T_sun=5772K, R_sun=1, a=1AU gives ~278K, matching the textbook
    zero-albedo estimate for Earth.
    """
    if not star_teff or not star_radius_solar or not a_au or a_au <= 0:
        return None
    SOLAR_RADIUS_IN_AU = 1 / 215.032
    r_star_au = star_radius_solar * SOLAR_RADIUS_IN_AU
    return star_teff * (r_star_au / (2 * a_au)) ** 0.5


def get_system(hostname: str) -> dict:
    hostname_escaped = hostname.replace("'", "''")
    cols = (
        "pl_name,pl_orbsmax,pl_orbeccen,pl_orbincl,pl_orbper,"
        "pl_rade,pl_bmasse,pl_eqt,"
        "st_teff,st_rad,st_mass,st_spectype,sy_dist"
    )
    adql = (
        f"select {cols} from ps "
        f"where default_flag=1 and hostname='{hostname_escaped}' "
        f"order by pl_orbsmax asc"
    )
    rows = _tap_query(adql)
    if not rows:
        return {"hostname": hostname, "found": False, "planets": [], "star": None}

    first = rows[0]
    star = {
        "teff_k": first.get("st_teff"),
        "radius_solar": first.get("st_rad"),
        "mass_solar": first.get("st_mass"),
        "spectral_type": first.get("st_spectype"),
        "distance_pc": first.get("sy_dist"),
    }
    hz = habitable_zone_au(star["teff_k"], star["radius_solar"])

    planets = []
    for r in rows:
        a_au = r.get("pl_orbsmax")
        period_days = r.get("pl_orbper")
        # Some planets (esp. radial-velocity detections) are missing semi-major
        # axis but have period + we have stellar mass — recover it via Kepler's
        # third law (a^3 = M_star * P_years^2, standard units AU/solar-mass/year)
        if a_au is None and period_days and star["mass_solar"]:
            period_years = period_days / 365.25
            a_au = (star["mass_solar"] * period_years ** 2) ** (1/3)

        radius_earth = r.get("pl_rade")
        mass_earth = r.get("pl_bmasse")
        eq_temp = r.get("pl_eqt")
        eq_temp_estimated = False
        if eq_temp is None:
            eq_temp = estimate_eq_temp_k(star["teff_k"], star["radius_solar"], a_au)
            eq_temp_estimated = eq_temp is not None
        esi = compute_esi(radius_earth, mass_earth, eq_temp)
        planet_type = classify_planet_type(radius_earth, mass_earth)

        in_hz = None
        if hz and a_au is not None:
            in_hz = hz["inner_au"] <= a_au <= hz["outer_au"]

        planets.append({
            "name": r.get("pl_name"),
            "a_au": a_au,
            "e": r.get("pl_orbeccen") or 0.0,
            "i_deg": r.get("pl_orbincl"),
            "period_days": period_days,
            "radius_earth": radius_earth,
            "mass_earth": mass_earth,
            "eq_temp_k": eq_temp,
            "eq_temp_estimated": eq_temp_estimated,
            "esi": esi,
            "in_habitable_zone": in_hz,
            "planet_type": planet_type,
        })

    return {
        "hostname": hostname,
        "found": True,
        "star": star,
        "habitable_zone_au": hz,
        "planets": planets,
    }
