# DCR Feasibility & Compliance System (Tamil Nadu)

A standalone tool to run **instant feasibility studies** on a plot against the Tamil Nadu
Combined Development & Building Rules, 2019 — and (later) check submitted drawings for compliance.

## Run it (Windows)

Double-click **`start.bat`**, then open <http://127.0.0.1:8000> in your browser.

Or manually:

```bat
cd backend
python -m pip install -r requirements.txt
python -m uvicorn api.main:app --port 8000
```

## What works today (v0.1)

- **Feasibility study** — enter plot area, dimensions, abutting road width, use → instant report:
  permissible FSI, setbacks (front/side/rear), buildable footprint, coverage %, max built-up area.
- **FMB upload** — renders the sketch and auto-fills cadastral fields when a text layer exists.
- **Setback overlay** — visual of the buildable envelope inside the plot.

Powered by **Rule 35** (Non-High-Rise) extracted from the Gazette.

## Project layout

```
backend/
  api/main.py            FastAPI app (feasibility + FMB endpoints)
  engine/feasibility.py  forward feasibility engine (rule-driven)
  engine/fmb.py          FMB PDF render + header parse
data/
  rules/*.json           machine-readable DCR rules (one file per rule)
  text/*.txt             extracted source text from the regulation PDFs
frontend/                browser UI (vanilla HTML/CSS/JS, offline)
```

## Deploy online (Render, team-only)

The app is containerized (`Dockerfile`) and ships a Render blueprint (`render.yaml`).

1. Push this folder to a **GitHub** repo (the `.gitignore` keeps source PDFs, the DB and temp files out).
2. In **Render** → *New + → Blueprint* → connect the repo. It reads `render.yaml` and builds the Docker image.
3. In the service's **Environment** tab, set **`APP_PASSWORD`** (your team's shared password). `APP_USER` defaults to `team`.
4. Deploy → you get `https://<name>.onrender.com`, HTTPS included. The browser will prompt for the team username/password.

Notes:
- **Persistence:** saved projects live on a 1 GB persistent disk at `/var/data` (set via `DB_PATH`). This needs the **`starter`** plan; on `free` the DB resets on redeploy.
- **Access gate:** Basic Auth is enforced only when `APP_PASSWORD` is set, so local runs stay open. `/api/health` is always public (for Render health checks).
- Same flow works on **Railway** (Docker) or any container host. For a self-managed **VPS**: `docker build -t dcr . && docker run -p 80:8000 -e APP_PASSWORD=... -v /srv/dcr-data:/var/data dcr`.

## Roadmap

- Finish rule extraction: parking (Annexure IV), OSR (Rule 41), FSI exclusions (Rule 29),
  High-Rise (Rule 39), then layer the 15 amendment GOs (newest wins).
- Shapely polygon-offset of the real FMB polygon (vs current rectangle approximation).
- PDF report export (client-ready), project/client history.
- Compliance module: parse submitted DXF / vector-PDF drawings and flag deviations.
