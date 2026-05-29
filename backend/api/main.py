"""
DCR System API.

Module 1 (live): Feasibility study  -> /api/feasibility, /api/fmb/parse
Future modules slot in as additional routers without touching this core:
  - Compliance check (submitted drawing vs rules)
  - Drawing parsing (DXF / vector PDF extraction)
  - Project & client history
"""
from __future__ import annotations
import os, sys

import hashlib, secrets
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

# make the backend package importable when launched via uvicorn from backend/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.feasibility import Plot, run_feasibility
from engine.scenarios import run_scenarios
from engine.compliance import Proposal, check_compliance
from engine import store
from engine.fmb import render_and_probe
from engine.dxf_import import parse_dxf
from engine.scrutiny import run_scrutiny
from engine.report_pdf import build_pdf
from engine import assistant
from fastapi import Response, Form

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_DIR = os.path.join(ROOT, "frontend")

APP_VERSION = "2.0-shape"
app = FastAPI(title="DCR Feasibility & Compliance System", version=APP_VERSION)

# --- team-only access gate (session cookie + login page; real logout) ---
# Enforced ONLY when APP_PASSWORD is set (so local dev stays open).
APP_USER = os.environ.get("APP_USER", "team")
APP_PASSWORD = os.environ.get("APP_PASSWORD")
SESSION_TOKEN = hashlib.sha256(f"dcr|{APP_USER}|{APP_PASSWORD}".encode()).hexdigest() if APP_PASSWORD else None
_PUBLIC = {"/api/login", "/api/logout", "/api/health"}

LOGIN_HTML = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>DCR — Team Login</title><style>
body{margin:0;font:15px/1.5 "Segoe UI",system-ui,sans-serif;background:#0f4c84;color:#1d2733;
display:grid;place-items:center;height:100vh}
.card{background:#fff;border-radius:14px;padding:30px 32px;width:320px;box-shadow:0 10px 40px rgba(0,0,0,.25)}
.logo{width:46px;height:46px;border-radius:10px;background:linear-gradient(135deg,#1668b3,#0f4c84);color:#fff;
font-weight:700;display:grid;place-items:center;margin-bottom:14px}
h1{font-size:17px;margin:0 0 2px}p{color:#66758a;font-size:12.5px;margin:0 0 18px}
label{display:block;font-size:12px;color:#66758a;margin:10px 0 4px}
input{width:100%;box-sizing:border-box;padding:10px;border:1px solid #e2e8f0;border-radius:8px;font:inherit}
button{width:100%;margin-top:18px;background:#1668b3;color:#fff;border:0;padding:11px;border-radius:9px;
font-size:15px;font-weight:600;cursor:pointer}button:hover{background:#0f4c84}
.err{color:#d94d3a;font-size:12.5px;margin-top:10px;min-height:16px}</style></head>
<body><form class=card onsubmit="return doLogin(event)">
<div class=logo>DCR</div><h1>Feasibility &amp; Compliance System</h1><p>Team access — please sign in.</p>
<label>Username</label><input id=u value="team" autocomplete=username>
<label>Password</label><input id=p type=password autocomplete=current-password autofocus>
<button type=submit>Sign in</button><div class=err id=e></div></form>
<script>async function doLogin(ev){ev.preventDefault();const e=document.getElementById('e');e.textContent='';
const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({username:document.getElementById('u').value,password:document.getElementById('p').value})});
if(r.ok){location.href='/';}else{e.textContent='Invalid username or password.';}return false;}</script>
</body></html>"""


@app.middleware("http")
async def team_gate(request: Request, call_next):
    path = request.url.path

    async def proceed():
        resp = await call_next(request)
        # never cache the app shell / scripts / styles, so deploys are always fresh
        if path == "/" or path.endswith((".js", ".css", ".html")):
            resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp

    if not APP_PASSWORD:
        return await proceed()
    if path in _PUBLIC or request.cookies.get("dcr_session") == SESSION_TOKEN:
        return await proceed()
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    return HTMLResponse(LOGIN_HTML, status_code=200)


@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    user = (data.get("username") or "").strip()
    pw = data.get("password") or ""
    if APP_PASSWORD and secrets.compare_digest(user, APP_USER) and secrets.compare_digest(pw, APP_PASSWORD):
        resp = JSONResponse({"ok": True})
        resp.set_cookie("dcr_session", SESSION_TOKEN, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
        return resp
    return JSONResponse({"ok": False, "detail": "Invalid credentials"}, status_code=401)


@app.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("dcr_session")
    return resp


class PlotIn(BaseModel):
    area_sqm: float = Field(gt=0)
    width_m: float = Field(gt=0)
    depth_m: float = Field(gt=0)
    abutting_road_width_m: float = Field(ge=0)
    use: str = "residential"
    area_type: str = "other_areas"
    parking_area_class: str = "corporation_municipal"
    dwellings: int = Field(default=1, ge=1)
    proposed_height_m: float | None = None
    survey_no: str | None = None
    village: str | None = None
    polygon: list | None = None
    front_edge_idx: int = 0
    plot_type: str = "individual"
    district: str | None = None
    road_sides: dict | None = None


class ProposalIn(BaseModel):
    plot: PlotIn
    height_m: float = Field(gt=0)
    dwellings: int = Field(default=1, ge=1)
    front_setback_m: float | None = None
    side_setback_m: float | None = None
    rear_setback_m: float | None = None
    built_up_area_sqm: float | None = None
    footprint_area_sqm: float | None = None
    car_parking_provided: int | None = None


class ScrutinyIn(BaseModel):
    plot_coords: list
    building_coords: list
    front_edge_idx: int = 0
    road_width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    floors: int = Field(default=1, ge=1)
    dwellings: int = Field(default=1, ge=1)
    use: str = "residential"
    area_class: str = "corporation_municipal"


class PdfIn(BaseModel):
    kind: str = "feasibility"
    meta: str = ""
    result: dict = {}


class SaveIn(BaseModel):
    client: str = ""
    title: str = ""
    kind: str = "feasibility"
    inputs: dict = {}
    result: dict = {}


@app.get("/api/health")
def health():
    from engine.amendments import status as amend_status
    return {"status": "ok", "version": APP_VERSION, "auth": bool(APP_PASSWORD),
            "modules": ["feasibility", "scenarios", "compliance", "projects"],
            "rules_loaded": ["Rule 35 (NHR)", "Rule 39 (HR)", "Rule 41 (OSR)", "Rule 49 (Premium FSI)", "Annexure IV (parking)"],
            "amendments_reviewed_through": amend_status()["reviewed_through"]}


@app.post("/api/feasibility")
def feasibility(plot: PlotIn):
    report = run_feasibility(Plot(**plot.model_dump()))
    return report


@app.post("/api/scenarios")
def scenarios(plot: PlotIn):
    return run_scenarios(Plot(**plot.model_dump()))


@app.post("/api/compliance")
def compliance(req: ProposalIn):
    plot = Plot(**req.plot.model_dump())
    prop = Proposal(height_m=req.height_m, dwellings=req.dwellings,
                    front_setback_m=req.front_setback_m, side_setback_m=req.side_setback_m,
                    rear_setback_m=req.rear_setback_m, built_up_area_sqm=req.built_up_area_sqm,
                    footprint_area_sqm=req.footprint_area_sqm, car_parking_provided=req.car_parking_provided)
    return check_compliance(plot, prop)


@app.post("/api/dxf/parse")
async def dxf_parse(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".dxf"):
        raise HTTPException(400, "Please upload a .dxf file (export DWG to DXF first).")
    data = await file.read()
    try:
        return parse_dxf(data)
    except Exception as e:  # noqa
        raise HTTPException(422, f"Could not read DXF: {e}")


@app.get("/api/assistant/status")
def assistant_status():
    return assistant.status()


@app.post("/api/assistant")
async def assistant_ask(question: str = Form(""), image: UploadFile | None = File(None)):
    img_bytes = await image.read() if image is not None else None
    media = image.content_type if image is not None else None
    try:
        return assistant.ask(question, img_bytes, media)
    except Exception as e:  # noqa
        raise HTTPException(502, f"Assistant error: {e}")


@app.post("/api/scrutiny")
def scrutiny(s: ScrutinyIn):
    return run_scrutiny(s.plot_coords, s.building_coords, s.front_edge_idx, s.road_width_m,
                        s.height_m, s.floors, s.dwellings, s.use, s.area_class)


@app.post("/api/report/pdf")
def report_pdf(p: PdfIn):
    pdf = build_pdf(p.kind, p.meta, p.result)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="DCR_{p.kind}_report.pdf"'})


@app.get("/api/projects")
def projects_list():
    return store.list_projects()


@app.post("/api/projects")
def projects_save(s: SaveIn):
    i = s.inputs
    return store.save_project(s.client, s.title, i.get("survey_no", ""), i.get("village", ""),
                              s.kind, s.inputs, s.result)


@app.get("/api/projects/{pid}")
def projects_get(pid: int):
    p = store.get_project(pid)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@app.delete("/api/projects/{pid}")
def projects_delete(pid: int):
    return {"deleted": store.delete_project(pid)}


@app.post("/api/fmb/parse")
async def fmb_parse(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload the FMB as a PDF.")
    data = await file.read()
    try:
        return render_and_probe(data)
    except Exception as e:  # noqa
        raise HTTPException(422, f"Could not read FMB PDF: {e}")


# serve the browser UI (mounted last so /api/* takes precedence)
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
