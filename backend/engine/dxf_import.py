"""
DXF drawing import. Reads a CAD .dxf, extracts closed polylines (candidate plot
boundary / building footprint), converts to metres via the file's $INSUNITS, and
returns candidates for the user to confirm (human-in-the-loop). The chosen polygon
feeds the same geometry engine used everywhere else.
"""
from __future__ import annotations
import io, math, os, tempfile
import ezdxf

# DXF $INSUNITS code -> metres-per-unit
_UNIT_TO_M = {0: None, 1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0,
              8: 1e-6, 9: 1e-3, 13: 1e-9, 14: 0.1, 15: 10.0, 16: 1000.0}
_UNIT_NAME = {0: "unitless", 1: "inches", 2: "feet", 4: "mm", 5: "cm", 6: "metres",
              14: "decimetres", 15: "decametres", 16: "km"}

# PreDCR / AutoDCR layer-name -> our object role (layer compared upper-case, leading underscores stripped)
PREDCR_LAYER_ROLES = {
    "plot": ["PLOT", "NETPLOT", "SITE", "SUBPLOT", "SUBDIVISION", "AMALGAMATION"],
    "building": ["BUILDING", "BLDGBLOCK", "PROPWORK", "MAIN", "PROPOSEDWORK"],
    "setback": ["MARGIN", "BUILDINGLINE", "UPPERSETBACK"],
    "parking": ["PARKING"],
    "road": ["ROAD", "INTERNALROAD", "INTDPROAD"],
    "osr": ["RECREATIONAL", "RESERVAREA"],
    "floor": ["FLOOR", "FLOORINSECTION"],
    "room": ["ROOM", "CARPET"],
    "staircase": ["STAIRCASE"],
    "compound": ["COMPOUND"],
}


def _role_for_layer(layer: str) -> str:
    key = layer.upper().lstrip("_").strip()
    for role, names in PREDCR_LAYER_ROLES.items():
        if key in names:
            return role
    return "other"


def _shoelace(pts):
    n = len(pts)
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def parse_dxf(data: bytes) -> dict:
    # ezdxf reads from a file path; handle both ASCII and binary DXF
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tf:
        tf.write(data)
        path = tf.name
    try:
        doc = ezdxf.readfile(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    scale = _UNIT_TO_M.get(insunits)
    units_known = scale is not None
    if scale is None:
        scale = 1.0  # assume metres; user can confirm

    msp = doc.modelspace()
    polylines = []
    for e in msp.query("LWPOLYLINE POLYLINE"):
        try:
            if e.dxftype() == "LWPOLYLINE":
                pts = [(p[0], p[1]) for p in e.get_points("xy")]
                closed = bool(e.closed)
            else:  # POLYLINE
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                closed = bool(e.is_closed)
        except Exception:
            continue
        if len(pts) < 3:
            continue
        pts_m = [[round(float(x) * scale, 3), round(float(y) * scale, 3)] for x, y in pts]
        xs = [p[0] for p in pts_m]; ys = [p[1] for p in pts_m]
        area = round(float(_shoelace(pts_m)), 2) if closed else 0.0
        polylines.append({
            "layer": str(e.dxf.layer), "role": _role_for_layer(str(e.dxf.layer)),
            "closed": closed, "vertex_count": len(pts_m),
            "area_sqm": area, "points": pts_m,
            "bbox": {"w": round(float(max(xs) - min(xs)), 2), "d": round(float(max(ys) - min(ys)), 2)},
        })

    closed_poly = [p for p in polylines if p["closed"] and p["area_sqm"] > 0]
    closed_poly.sort(key=lambda p: p["area_sqm"], reverse=True)

    def _suggest(role):
        cands = [p for p in closed_poly if p["role"] == role]
        return polylines.index(cands[0]) if cands else None

    # prefer PreDCR layer roles; fall back to area (largest=plot, 2nd=building)
    suggested_plot = _suggest("plot")
    if suggested_plot is None and closed_poly:
        suggested_plot = polylines.index(closed_poly[0])
    suggested_building = _suggest("building")
    if suggested_building is None:
        others = [p for p in closed_poly if polylines.index(p) != suggested_plot]
        suggested_building = polylines.index(others[0]) if others else None
    layers_detected = sorted({p["role"] for p in polylines if p["role"] != "other"})

    return {
        "units": {"code": insunits, "name": _UNIT_NAME.get(insunits, f"code {insunits}"),
                  "metres_per_unit": scale, "known": units_known},
        "polyline_count": len(polylines),
        "polylines": polylines,
        "roles_detected": layers_detected,
        "suggested_plot_idx": suggested_plot,
        "suggested_building_idx": suggested_building,
        "note": "Geometry converted to metres." + ("" if units_known else " Units were unitless — assumed metres; please confirm."),
    }
