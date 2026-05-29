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

import base64, secrets
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.staticfiles import StaticFiles
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
from fastapi import Response

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_DIR = os.path.join(ROOT, "frontend")

APP_VERSION = "1.1-depthfix"
app = FastAPI(title="DCR Feasibility & Compliance System", version=APP_VERSION)

# --- team-only access gate (HTTP Basic Auth) ---
# Enforced ONLY when APP_PASSWORD is set (so local dev stays open).
APP_USER = os.environ.get("APP_USER", "team")
APP_PASSWORD = os.environ.get("APP_PASSWORD")


@app.middleware("http")
async def team_gate(request: Request, call_next):
    if APP_PASSWORD and request.url.path != "/api/health":
        ok = False
        hdr = request.headers.get("authorization", "")
        if hdr.startswith("Basic "):
            try:
                user, pw = base64.b64decode(hdr[6:]).decode("utf-8").split(":", 1)
                ok = secrets.compare_digest(user, APP_USER) and secrets.compare_digest(pw, APP_PASSWORD)
            except Exception:
                ok = False
        if not ok:
            from fastapi import Response as _R
            return _R(status_code=401, headers={"WWW-Authenticate": 'Basic realm="DCR team access"'})
    return await call_next(request)


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
    return {"status": "ok", "version": APP_VERSION,
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
