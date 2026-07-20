"""
Solar system reference data.

Planet orbital elements are the standard JPL/Standish "Keplerian Elements
for Approximate Positions of the Major Planets" (heliocentric, ecliptic
J2000 frame, valid roughly 1800-2050). This is the correct physics model
for planets — two-body Keplerian motion, not SGP4 (which exists
specifically to handle atmospheric drag and other perturbations on
Earth-orbiting satellites, and doesn't apply to planets at all).

These values are reproduced from memory/training data rather than
fetched live from JPL, so treat them as good for visualization — not
survey-grade precision. For research-grade accuracy, swap this out for
live JPL Horizons API queries (https://ssd.jpl.nasa.gov/api/horizons.api),
which is a clean upgrade path that doesn't require changing anything
downstream of this module.

Elements at epoch, and their rates of change per Julian century, in the
form: a (AU), e, I (deg), L (deg), long_peri (deg), long_node (deg).
"""

PLANETS = {
    "mercury": {
        "elements": {"a": 0.38709927, "e": 0.20563593, "i": 7.00497902, "L": 252.25032350, "long_peri": 77.45779628, "long_node": 48.33076593},
        "rates":    {"a": 0.00000037, "e": 0.00001906, "i": -0.00594749, "L": 149472.67411175, "long_peri": 0.16047689, "long_node": -0.12534081},
        "radius_km": 2439.7, "mass_earth": 0.055, "rotation_hours": 1407.6,
        "color": "#b1a8a0", "moons": [],
    },
    "venus": {
        "elements": {"a": 0.72333566, "e": 0.00677672, "i": 3.39467605, "L": 181.97909950, "long_peri": 131.60246718, "long_node": 76.67984255},
        "rates":    {"a": 0.00000390, "e": -0.00004107, "i": -0.00078890, "L": 58517.81538729, "long_peri": 0.00268329, "long_node": -0.27769418},
        "radius_km": 6051.8, "mass_earth": 0.815, "rotation_hours": -5832.5,
        "color": "#e8c99b", "moons": [],
    },
    "earth": {
        "elements": {"a": 1.00000261, "e": 0.01671123, "i": -0.00001531, "L": 100.46457166, "long_peri": 102.93768193, "long_node": 0.0},
        "rates":    {"a": 0.00000562, "e": -0.00004392, "i": -0.01294668, "L": 35999.37244981, "long_peri": 0.32327364, "long_node": 0.0},
        "radius_km": 6371.0, "mass_earth": 1.0, "rotation_hours": 23.93,
        "color": "#4f9de0", "moons": ["moon"],
    },
    "mars": {
        "elements": {"a": 1.52371034, "e": 0.09339410, "i": 1.84969142, "L": -4.55343205, "long_peri": -23.94362959, "long_node": 49.55953891},
        "rates":    {"a": 0.00001847, "e": 0.00007882, "i": -0.00813131, "L": 19140.30268499, "long_peri": 0.44441088, "long_node": -0.29257343},
        "radius_km": 3389.5, "mass_earth": 0.107, "rotation_hours": 24.62,
        "color": "#c1440e", "moons": ["phobos", "deimos"],
    },
    "jupiter": {
        "elements": {"a": 5.20288700, "e": 0.04838624, "i": 1.30439695, "L": 34.39644051, "long_peri": 14.72847983, "long_node": 100.47390909},
        "rates":    {"a": -0.00011607, "e": -0.00013253, "i": -0.00183714, "L": 3034.74612775, "long_peri": 0.21252668, "long_node": 0.20469106},
        "radius_km": 69911.0, "mass_earth": 317.8, "rotation_hours": 9.93,
        "color": "#d8ac6e", "moons": ["io", "europa", "ganymede", "callisto"],
    },
    "saturn": {
        "elements": {"a": 9.53667594, "e": 0.05386179, "i": 2.48599187, "L": 49.95424423, "long_peri": 92.59887831, "long_node": 113.66242448},
        "rates":    {"a": -0.00125060, "e": -0.00050991, "i": 0.00193609, "L": 1222.49362201, "long_peri": -0.41897216, "long_node": -0.28867794},
        "radius_km": 58232.0, "mass_earth": 95.2, "rotation_hours": 10.7,
        "color": "#e3d3a5", "moons": ["titan", "enceladus"],
    },
    "uranus": {
        "elements": {"a": 19.18916464, "e": 0.04725744, "i": 0.77263783, "L": 313.23810451, "long_peri": 170.95427630, "long_node": 74.01692503},
        "rates":    {"a": -0.00196176, "e": -0.00004397, "i": -0.00242939, "L": 428.48202785, "long_peri": 0.40805281, "long_node": 0.04240589},
        "radius_km": 25362.0, "mass_earth": 14.5, "rotation_hours": -17.24,
        "color": "#9fd9d9", "moons": ["titania"],
    },
    "neptune": {
        "elements": {"a": 30.06992276, "e": 0.00859048, "i": 1.77004347, "L": -55.12002969, "long_peri": 44.96476227, "long_node": 131.78422574},
        "rates":    {"a": 0.00026291, "e": 0.00005105, "i": 0.00035372, "L": 218.45945325, "long_peri": -0.32241464, "long_node": -0.00508664},
        "radius_km": 24622.0, "mass_earth": 17.1, "rotation_hours": 16.11,
        "color": "#5b7fe0", "moons": ["triton"],
    },
}

# Moons: simplified relative-to-parent orbits (near-circular approximation
# for most; period/eccentricity are real published values, but each moon's
# *current phase* — where exactly it sits in its orbit right now — is
# illustrative, not tied to a real epoch anomaly. Good enough to show
# correct scale, period, and shape; not for predicting a real transit.
MOONS = {
    "moon":      {"parent": "earth",   "a_km": 384400,   "e": 0.0549,   "i_deg": 5.14,   "period_days": 27.32,  "radius_km": 1737.4, "color": "#c9c9c9"},
    "phobos":    {"parent": "mars",    "a_km": 9376,     "e": 0.0151,   "i_deg": 1.08,   "period_days": 0.319,  "radius_km": 11.1,   "color": "#8a7a6a"},
    "deimos":    {"parent": "mars",    "a_km": 23463,    "e": 0.00033,  "i_deg": 1.79,   "period_days": 1.263,  "radius_km": 6.2,    "color": "#8a7a6a"},
    "io":        {"parent": "jupiter", "a_km": 421800,   "e": 0.0041,   "i_deg": 0.04,   "period_days": 1.769,  "radius_km": 1821.6, "color": "#e6d17a"},
    "europa":    {"parent": "jupiter", "a_km": 671100,   "e": 0.009,    "i_deg": 0.47,   "period_days": 3.551,  "radius_km": 1560.8, "color": "#d9c7a3"},
    "ganymede":  {"parent": "jupiter", "a_km": 1070400,  "e": 0.0013,   "i_deg": 0.20,   "period_days": 7.155,  "radius_km": 2634.1, "color": "#a89a8a"},
    "callisto":  {"parent": "jupiter", "a_km": 1882700,  "e": 0.0074,   "i_deg": 0.19,   "period_days": 16.69,  "radius_km": 2410.3, "color": "#7a6f63"},
    "titan":     {"parent": "saturn",  "a_km": 1221870,  "e": 0.0288,   "i_deg": 0.33,   "period_days": 15.945, "radius_km": 2574.7, "color": "#e0b866"},
    "enceladus": {"parent": "saturn",  "a_km": 238020,   "e": 0.0047,   "i_deg": 0.02,   "period_days": 1.370,  "radius_km": 252.1,  "color": "#eef5f7"},
    "titania":   {"parent": "uranus",  "a_km": 436300,   "e": 0.0011,   "i_deg": 0.34,   "period_days": 8.706,  "radius_km": 788.4,  "color": "#b7bfc7"},
    "triton":    {"parent": "neptune", "a_km": 354759,   "e": 0.000016, "i_deg": 157.0,  "period_days": -5.877, "radius_km": 1353.4, "color": "#dfe8ea"},  # retrograde
}

SUN = {"radius_km": 696340.0, "color": "#ffd166"}
