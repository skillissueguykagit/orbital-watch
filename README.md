# SSA Dashboard — v0.1 (Version 2 of your roadmap)

A live, real satellite map: FastAPI backend pulls TLE data from CelesTrak
and propagates true orbital positions with SGP4 (via `skyfield`). Frontend
is a single-file Three.js dashboard, no build step required.

## Run it

**Backend**
```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Check it's alive: http://localhost:8000/api/health

**Frontend**
Just open `frontend/index.html` directly in a browser (double-click it,
or `open frontend/index.html`). It talks to `http://localhost:8000` by
default — change `API_BASE` at the top of the `<script>` block if you
deploy the backend elsewhere.

## What's actually happening

- `GET /api/satellites?group=stations` fetches current TLEs for a group
  (stations / visual / active / debris), propagates each one to *right
  now* with SGP4, and returns lat/lon/altitude/speed.
- The frontend polls this every 15s, converts lat/lon/alt to 3D
  coordinates, and plots each object on a rotating Earth.
- Click any dot to see its telemetry in the side panel.
- `GET /api/satellite/{norad_id}/predict` already exists and forward-
  propagates a single object's ground track — this is your hook into
  Phase 3 (orbit prediction) and eventually Phase 4 (collision warning):
  run `predict` for two objects, walk their tracks forward together, and
  flag any timestep where the 3D distance between them drops under a
  threshold. That's a real (if simplified) conjunction-screening
  algorithm — no different in spirit from what actual SSA systems do at
  the first-pass stage.

## Where to go next, in order of payoff

1. **Swap `group=stations` for `group=active`** once you've confirmed
   things work — that's thousands of real satellites instead of ~12.
   Render perf note: at that scale, switch satellite rendering from
   individual meshes to a single `THREE.Points` buffer (one draw call
   instead of thousands).
2. **Wire up `/predict` in the UI** — when a satellite is selected, fetch
   its predicted track and draw it as a `THREE.Line` arcing ahead of the
   dot. This is Phase 3, and you already have the endpoint.
3. **Collision screening (Phase 4)** — call `/predict` for every pair of
   objects in a group (or just debris vs. active satellites, to keep it
   tractable), compare positions at matching timestamps, and flag any
   pair whose minimum separation drops below, say, 5 km. Surface it as
   an ALERT banner in the UI.
4. **Phase 1 (actual computer vision on telescope footage)** is a
   separate, harder track — it needs either real telescope video or a
   public dataset (search for "space object detection dataset" /
   SPARK/SPADE-style datasets used in SSA research) before YOLO has
   anything to learn from. Worth doing as its own sprint once the
   orbital-mechanics side of the dashboard feels solid — you don't need
   it to have a legitimately impressive project.

## Notes

- CelesTrak TLEs are cached in-memory for 6 hours (TLEs are only
  accurate for ~1-2 days anyway, so no need to refetch every request).
- If satellites don't load: open the browser console — 99% of the time
  it's either the backend not running, or a CORS/network block. The
  status badge in the bottom-left of the UI will also tell you if the
  feed is offline.

## New: pass prediction ("when can I actually see this thing?")

`GET /api/passes?norad_id=&lat=&lon=&group=` scans the next 72h for windows
where the satellite climbs above 10° elevation from your location, then
checks two real conditions for naked-eye visibility:
- Is the satellite sunlit (not in Earth's shadow)?
- Is your sky dark enough (sun below -6°, civil twilight or darker)?

This needs a JPL ephemeris file (`de421.bsp`, ~17MB) to know where the Sun
is — `skyfield` downloads it automatically on first call and caches it in
`backend/skyfield-data/`. That means the **first** pass-prediction request
needs internet access and will take a few seconds; every request after
that is instant.

Set your location either by clicking "📍 USE MY LOCATION" (browser
geolocation) or by clicking anywhere on the 3D globe — a violet marker
shows where you've set. Then click any satellite dot; if you can see the
sky, you'll get a real list of upcoming passes with time, peak elevation,
compass direction, and whether it'll actually be visible.

## New: quality-of-life additions

- Every left-side panel can collapse (the "–" toggle in its header) to
  reduce clutter once you've got several open at once.
- "⟲ RESET VIEW" in the top bar snaps the camera back to the default
  overview after you've flown to a satellite.
- Hovering any satellite dot shows its name in a small tooltip — handy
  for browsing without committing to a click.
- "clear" link next to the match count resets search text + altitude
  band filters in one click.
- Press `/` anywhere to jump into the search box (same muscle memory as
  Slack/GitHub/etc).
- A small legend (bottom-right) explains what each marker color/shape
  means — cyan, red, gold, amber, violet.

## New: run it with Docker (no manual venv/pip needed)

```bash
docker compose up --build
```

That's it. It builds and starts both services:
- Backend on `http://localhost:8000`
- Frontend on `http://localhost:8080`

Open `http://localhost:8080` in a browser — the page still talks to
`http://localhost:8000` under the hood, which works fine since both ports
are published to your host machine.

Notes:
- The ephemeris file (`de421.bsp`) downloads into `backend/skyfield-data/`
  on first pass-prediction request, same as before — this folder is
  mounted as a volume so it survives `docker compose down` / restarts and
  won't re-download every time.
- `docker compose down` stops both containers. Add `-v` only if you
  actually want to wipe the ephemeris cache volume too.
- If you change `main.py` or `index.html`, re-run with `--build` to pick
  up the changes (or add `--watch` / bind-mounts later if you want live
  reload — not set up by default here to keep the compose file simple).

## New: live weather imagery overlay

Click "🌤 SHOW LIVE WEATHER" in the left panel to swap the Earth texture
for NASA GIBS' daily true-color satellite composite — real MODIS imagery,
no API key needed. Cloud cover is visible directly in true-color imagery,
so this doubles as an actual "what does the sky look like today" layer,
not just decoration.

Caveats worth knowing:
- It's a **daily** whole-Earth composite (~1 day latency), not live radar
  — good enough to eyeball "is it cloudy over my area right now," not
  precise enough for minute-by-minute forecasting.
- If the button says "unavailable," it's almost always a CORS or network
  hiccup talking to NASA's GIBS servers — check the browser console for
  the specific failure; it doesn't affect anything else in the app.

## New: draggable / resizable panels

Every panel (tracked objects, search, live events, selected-satellite
details, conjunction alerts, legend) can now be:
- **Dragged** by its header — click and hold the title bar, move it
  anywhere on screen.
- **Resized** from the small grip in its bottom-right corner (except the
  legend, which is fixed-size — its content doesn't really benefit from
  resizing).
- **Brought to front** by clicking anywhere on it, so an overlapping
  panel is never permanently stuck behind another one.
- **Reset** — "⊞ RESET LAYOUT" in the top bar snaps every panel back to
  its original position and size in one click.

Scope note: panels don't *physically* push each other out of the way
when dragged (that's a much fussier "tiling window manager" feature) —
they can overlap if you drag them on top of each other, but bring-to-
front + Reset Layout make that easy to deal with rather than something
that needs preventing outright.

## New: Solar System mode

Click "☀ SOLAR SYSTEM" in the top bar to switch views. This is a
genuinely separate mode, not decoration:

- **Real orbital mechanics** — the standard JPL/Standish Keplerian
  elements for all 8 planets (heliocentric, J2000 epoch), propagated
  with an actual Kepler-equation solver. This is the correct physics
  model for planets (two-body motion), as opposed to satellites, which
  need SGP4 specifically to handle atmospheric drag.
- **Major moons** — Earth's Moon, Phobos/Deimos, the four Galilean
  moons, Titan/Enceladus, Titania, and Triton — with real distances,
  periods, and eccentricities. Their exact *current phase* (where in
  the orbit they sit right now) is illustrative rather than tied to a
  precise epoch anomaly — everything else about them (scale, period,
  shape, even Triton's retrograde motion) is real.
- **Time controls** — pause, or run the simulation at 1/10/100 days-per-
  second or 1 year-per-second, with a live simulated-date readout and a
  one-click "jump to today."
- **Click any body** for a real info panel — radius, mass, day length,
  orbital period (via Kepler's third law), moon count.
- Distances and sizes are **compressed for visibility** (sqrt-scale
  distances, cube-root-scale radii) — none of this is rendered to true
  physical scale, which is standard practice for solar system
  visualizers (true-to-scale would make every planet a sub-pixel dot
  across mostly-empty space).

Backend: new `backend/solar_system.py` module holding the orbital
element / physical-fact tables, served via `GET /api/solar-system` —
**make sure this new file is in your `backend/` folder**, and if you're
on Docker, rebuild (`docker compose up --build`) since the Dockerfile
now copies two Python files instead of one.

## What's next (planned): exoplanet habitability viewer

Reframed from the original SpaceApps idea: rather than placing
exoplanets at their true (meaningless-at-this-scale) galactic position,
the plan is a **per-star-system orbit view** — pick a star, see its
planets orbit it, exactly like the solar system view above, reusing
the same Kepler math. Real data from NASA's Exoplanet Archive, plus
a habitability scoring method (pending confirmation of the exact
formula/factors from the original SpaceApps project).

## New: Exoplanet viewer

Click "🪐 EXOPLANETS" in the top bar. Real, live data from NASA's
Exoplanet Archive (public TAP API, no key needed) — search any confirmed
star system by name, or start from a featured list (TRAPPIST-1,
Kepler-186, Proxima Cen, etc.).

- **Per-star-system orbit view** — reframed from the original idea of
  placing exoplanets at their true galactic position (meaningless at
  this visual scale, since everything's light-years away). Instead: pick
  a star, see its planets orbit it, exactly like the solar system view —
  and it reuses the exact same Kepler solver.
- **Earth Similarity Index (ESI)** — a real, published habitability
  score (Schulze-Makuch et al. 2011), not a custom formula, since the
  original SpaceApps methodology wasn't recoverable. Verified against
  known values before shipping: Earth scores 1.0, Mars ~0.66, Venus
  ~0.44 — matches published ESI tables. See `backend/exoplanets.py` for
  the method and how to swap in a different formula later if you find
  your original one.
- **Habitable zone shading** — a translucent ring around the star
  showing the (conservative, simplified) habitable zone bounds, so you
  can see at a glance which planets fall inside it.
- Click any planet for its ESI score, habitable-zone status, radius,
  mass, equilibrium temperature, and orbital period.

Honest limitations: most exoplanets are missing orbital orientation data
(longitude of ascending node, argument of periapsis) that we have for
solar system planets, so orbits here use a simplified 2-angle model
(inclination only) rather than the full 3-angle one — visually similar,
not survey-grade. Planet "current position in orbit" is illustrative for
the same reason as the solar system moons: real epoch/phase data isn't
part of what the Archive publishes for most planets.

Backend: new `backend/exoplanets.py` — **make sure this file is in your
`backend/` folder** alongside `main.py` and `solar_system.py`. Docker
users: rebuild (`docker compose up --build`), the Dockerfile now copies
three Python files.

## New: expanded satellite categories + real object-type classification

**More categories** — the group selector now covers 20+ CelesTrak
groups organized into General / Constellations / Navigation-Comms /
Earth Observation-Science / Debris Fields, including Iridium NEXT,
Globalstar, Orbcomm, Planet Labs, Spire, Intelsat, SES, and SatNOGS
alongside what was already there.

**Four real debris clouds, not one** — beyond Cosmos 1408, you can now
load:
- Fengyun-1C debris (2007 Chinese ASAT test — among the largest
  debris-generating events in history)
- Iridium 33 debris (the active-satellite side of the 2009 Iridium/
  Cosmos collision)
- Cosmos 2251 debris (the defunct-satellite side of that same collision)

**Real object-type classification** — every satellite record now
carries an `object_type` field (Payload / Rocket Body / Debris),
parsed from CelesTrak's actual naming convention (`DEB`, `R/B` suffixes)
rather than a rough guess. This applies across *every* group, not just
the dedicated debris ones — load "active" and you'll still see rocket
bodies show up correctly tagged. Rocket bodies now render in amber,
distinct from cyan payloads and red debris, and there's a new type
filter (Payload / Rocket Body / Debris / All) in the search panel
alongside the altitude-band filter.

**Note**: the old `debris` group key was renamed to `cosmos-1408-debris`
for clarity now that there are four debris groups — if you had anything
hardcoded against the old name (unlikely unless you modified the code
yourself), update it to the new key.

## Deploying it for real (a shareable link)

Recommended: **Render.com** — free tier, deploys straight from your
existing Dockerfiles, no separate hosting knowledge required. This repo
now includes everything needed for it.

### 1. Push to GitHub

Render deploys from a Git repo, not a direct file upload.

```bash
cd ssa-dashboard
git init
git add .
git commit -m "Initial commit"
```
Create a new repo on github.com (empty, no README), then:
```bash
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git
git branch -M main
git push -u origin main
```

### 2. Deploy via Render Blueprint

1. Sign up at render.com (free, no credit card needed for the free tier).
2. Dashboard → **New** → **Blueprint**.
3. Connect your GitHub account and pick the repo you just pushed.
4. Render finds `render.yaml` automatically and proposes two services:
   `ssa-backend` and `ssa-frontend`. Click **Apply**.
5. Wait for both to build (the backend build takes a few minutes the
   first time — it's installing `skyfield`, which compiles some things).

### 3. Connect frontend to backend

Once `ssa-backend` finishes deploying, copy its URL from the Render
dashboard (looks like `https://ssa-backend-xxxx.onrender.com`).

Edit `frontend/index.html`, find this line near the top of the
`<script>` block:
```js
const PRODUCTION_API_BASE = "https://YOUR-BACKEND-URL.onrender.com";
```
Replace it with your actual backend URL, then:
```bash
git add frontend/index.html
git commit -m "Point frontend at deployed backend"
git push
```
Render auto-redeploys the frontend on every push. Once that finishes,
your `ssa-frontend` URL is a real, shareable link.

### What to expect on the free tier

- **Cold starts**: free services sleep after 15 minutes of no traffic.
  The first request after that takes 30-60 seconds to wake up — normal,
  not broken. Share the link a minute before you actually need to demo it.
- **No persistent disk on free tier**: the ephemeris file (de421.bsp)
  re-downloads after each cold start instead of staying cached. Adds a
  few seconds to the first pass-prediction request post-sleep; harmless.
- **CORS is wide open** (`allow_origins=["*"]"` in `main.py`) — fine for
  a personal/demo project, worth tightening if this ever becomes
  something with real users.

If you outgrow the free tier's cold starts later, the code doesn't need
to change — just upgrade the Render plan (or move to Railway/Fly.io;
the Dockerfiles work anywhere that runs containers).
