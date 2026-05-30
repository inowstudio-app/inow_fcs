"""
Forward feasibility engine for TN DCR.
compute_envelope() is the core: given a plot + a development intent (building class,
dwellings, height) it returns the permissible envelope with the rule clauses cited.
run_feasibility() runs it for one intent; scenarios.py runs it across candidate uses.
"""
from __future__ import annotations
import json, math, os
from dataclasses import dataclass

from .parking import estimate_parking
from .geometry import rect_coords, buildable
from . import amendments
from . import obligations

RULES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "rules")


def _load(rule_file: str) -> dict:
    with open(os.path.join(RULES_DIR, rule_file), encoding="utf-8") as f:
        return json.load(f)


def osr_requirement(plot_area: float) -> dict:
    r = _load("rule_41_osr.json")
    for b in r["bands"]:
        cap = b["site_area_upto_sqm"]
        if cap is None or plot_area <= cap + 1e-9:
            if b.get("osr") == "nil":
                return {"required_sqm": 0.0, "pct": 0, "note": "No OSR below 3,000 m²", "source": "Rule 41"}
            return {"required_sqm": round(b["osr_pct"] / 100 * plot_area, 1), "pct": b["osr_pct"],
                    "min_parcel_sqm": b.get("min_parcel_sqm"), "min_width_m": b.get("min_width_m"),
                    "payment_in_lieu": b.get("payment_in_lieu_allowed"), "note": b.get("note"), "source": "Rule 41"}
    return {"required_sqm": 0.0, "pct": 0, "source": "Rule 41"}


def premium_fsi(road_width: float, normal_fsi_bua: float, building_class: str) -> dict:
    r = _load("rule_49_premium_fsi.json")
    for b in r["premium_by_road_width_m"]:
        if road_width >= b["road_min_m"] - 1e-9:
            cls = "high_rise" if building_class == "high_rise" else "non_high_rise"
            return {"premium_pct": b["premium_pct"], "upside_sqm": round(b["premium_pct"] / 100 * normal_fsi_bua, 1),
                    "charge_basis": r["charge_basis"][cls], "source": "Rule 49"}
    return {"premium_pct": 0, "upside_sqm": 0.0, "note": "Road < 9 m: no Premium FSI", "source": "Rule 49"}


@dataclass
class Plot:
    area_sqm: float
    width_m: float
    depth_m: float
    abutting_road_width_m: float
    use: str = "residential"
    area_type: str = "other_areas"            # other_areas | continuous_building_area | ews
    parking_area_class: str = "corporation_municipal"  # or "panchayat"
    dwellings: int = 1
    proposed_height_m: float | None = None
    survey_no: str | None = None
    village: str | None = None
    polygon: list | None = None      # optional explicit corner points [[x,y],...] in metres
    front_edge_idx: int = 0          # which polygon edge abuts the road
    plot_type: str = "individual"    # individual | gated (approved-layout)
    district: str | None = None      # for location-specific rules (Build B)
    road_sides: dict | None = None   # {"N":width,"E":width,...} abutting roads (for report)
    has_stilt: bool = False          # open stilt parking floor (FSI/height-exempt)


def _pick(bands, value, key, out):
    for b in bands:
        cap = b.get(key)
        if cap is None or value <= cap + 1e-9:
            return b[out]
    return bands[-1][out]


# ---------- Non-High-Rise (Rule 35) ----------
def _envelope_non_high_rise(plot: Plot, dwellings: int, height: float) -> dict:
    r = _load("rule_35_non_high_rise.json")
    cat = next(c for c in r["categories"] if c["id"] == ("35.1.a" if dwellings <= 16 and height <= 14 else "35.1.b"))
    flags = []
    if cat["id"] == "35.1.a":
        fsb = _pick(cat["front_setback_by_road_width_m"], plot.abutting_road_width_m, "road_upto_m", "fsb_m")
        ssb = 0.0; sides = "either"
        for hb in cat["side_setback_m"]["by_height_and_plot_width"]:
            if height <= hb["height_upto_m"] + 1e-9:
                for band in hb["bands"]:
                    if band.get("plot_width_upto_m") is None or plot.width_m <= band["plot_width_upto_m"] + 1e-9:
                        ssb = band["ssb_m"]; sides = band["sides"]; break
                break
        rsb = _pick(cat["rear_setback_by_height_m"], height, "height_upto_m", "rsb_m")
    else:
        fsb = _pick(cat["front_setback_by_road_width_m"], plot.abutting_road_width_m, "road_upto_m", "fsb_m")
        srb = _pick(cat["side_and_rear_setback_by_height_m"], height, "height_upto_m", "setback_m")
        ssb = rsb = srb; sides = "either"
        if plot.abutting_road_width_m < cat["min_road_width_m"]:
            flags.append(f"Road {plot.abutting_road_width_m}m < required {cat['min_road_width_m']}m for >16 dwellings.")
    return {"rule": "TNCDBR-2019 Rule 35 (" + cat["id"] + ")", "fsi": cat["fsi_max"],
            "fsb": fsb, "ssb": ssb, "side_applies": sides, "rsb": rsb,
            "max_coverage_pct": None, "flags": flags,
            "max_height_m": 14.0 if cat["id"] == "35.1.a" else 18.30,
            "max_floors": 3 if cat["id"] == "35.1.a" else max(1, int(height // 3.0))}


# ---------- High-Rise (Rule 39) ----------
def _envelope_high_rise(plot: Plot, height: float) -> dict:
    r = _load("rule_39_high_rise.json")
    flags = []
    rw = plot.abutting_road_width_m
    eligible = [b for b in r["fsi_by_road_width_m"] if rw >= b["road_min_m"] - 1e-9]
    if not eligible:
        return {"allowed": False, "reason": f"High-rise needs road >= 12m; have {rw}m.", "flags": flags}
    fsi = max(b["fsi"] for b in eligible)
    sb = r["setback_all_around_m"]["height_upto_30m"]
    if height > 30:
        sb = min(20.0, sb + math.ceil((height - 30) / 6.0))
    return {"rule": "TNCDBR-2019 Rule 39", "fsi": fsi, "fsb": sb, "ssb": sb, "side_applies": "either",
            "rsb": sb, "max_coverage_pct": r["max_coverage_pct"], "flags": flags, "allowed": True,
            "max_height_m": height, "max_floors": max(1, int(height // 3.0))}


# ---------- Generic envelope computation ----------
def compute_envelope(plot: Plot, building_class: str, dwellings: int, height: float) -> dict:
    if building_class == "high_rise":
        e = _envelope_high_rise(plot, height)
        if not e.get("allowed", True):
            return {"allowed": False, "reason": e["reason"], "building_class": building_class}
    else:
        e = _envelope_non_high_rise(plot, dwellings, height)

    # --- exact geometry: offset the real plot polygon edge-by-edge ---
    coords = plot.polygon if plot.polygon else rect_coords(plot.width_m, plot.depth_m)
    bcoords, footprint, plot_area_geo = buildable(
        coords, plot.front_edge_idx, e["fsb"], e["ssb"], e["rsb"], e["side_applies"])
    plot_area = plot.area_sqm or plot_area_geo
    cov_flag = None
    if e.get("max_coverage_pct") and footprint > e["max_coverage_pct"] / 100 * plot_area:
        footprint = round(e["max_coverage_pct"] / 100 * plot_area, 2)
        cov_flag = f"Footprint capped to {e['max_coverage_pct']}% coverage (Rule 39)."

    if footprint <= 1.0:
        return {"allowed": False, "building_class": building_class,
                "reason": f"Setbacks ({e['fsb']}/{e['ssb']}/{e['rsb']} m) leave no buildable area on this plot."}

    fsi_bua = e["fsi"] * plot_area
    physical_bua = footprint * e["max_floors"]
    bua = min(fsi_bua, physical_bua)
    parking = estimate_parking(plot.use, bua, dwellings, plot.parking_area_class)
    flags = list(e["flags"]) + ([cov_flag] if cov_flag else [])

    # --- floor stack for the elevation: fill full floors bottom-up until the
    # governing BUA is used; the top floor steps back only if FSI is the binding
    # limit (footprint x floors > FSI cap). Deterministic, proportional. ---
    FLOOR_HEIGHT_M = 3.0
    floor_areas = []
    rem = bua
    for _ in range(e["max_floors"]):
        a = min(footprint, rem)
        if a <= 0.5:
            break
        floor_areas.append(round(a, 2))
        rem -= a
    elevation = {
        "max_height_m": e.get("max_height_m", e["max_floors"] * FLOOR_HEIGHT_M),
        "floor_height_m": FLOOR_HEIGHT_M,
        "built_height_m": round(len(floor_areas) * FLOOR_HEIGHT_M, 2),
        "footprint_sqm": round(footprint, 2),
        "floor_areas_sqm": floor_areas,
        "top_stepped": len(floor_areas) > 1 and floor_areas[-1] < floor_areas[0] - 0.5,
        "fsi_headroom_sqm": round(max(0.0, fsi_bua - bua), 1),
    }

    return {
        "allowed": True, "building_class": building_class, "rule": e["rule"], "fsi": e["fsi"],
        "height_m": height, "dwellings": dwellings,
        "setbacks_m": {"front": e["fsb"], "side": e["ssb"], "side_applies": e["side_applies"], "rear": e["rsb"]},
        "geometry": {"plot": coords, "buildable": bcoords, "front_edge_idx": plot.front_edge_idx},
        "buildable_footprint": {"area_sqm": round(footprint, 2),
                                 "coverage_pct": round(100 * footprint / plot_area, 1)},
        "max_built_up_area_sqm": {"governing": round(bua, 1), "fsi_limit": round(fsi_bua, 1),
                                   "physical_limit": round(physical_bua, 1), "max_floors": e["max_floors"]},
        "parking": parking,
        "elevation": elevation,
        "obligations": obligations.summarize(obligations.checklist(
            plot.use, building_class, plot_area, plot.abutting_road_width_m,
            dwellings, height, e["max_floors"], bua, getattr(plot, "has_stilt", False))),
        "eligibility": obligations.eligibility(
            building_class, plot_area, plot.abutting_road_width_m, dwellings, height),
        "osr": osr_requirement(plot_area),
        "premium_fsi": premium_fsi(plot.abutting_road_width_m, fsi_bua, building_class),
        "advisories": amendments.advisories(plot.use, bua, dwellings),
        "flags": flags,
    }


def run_feasibility(plot: Plot) -> dict:
    height = plot.proposed_height_m or 11.0
    bclass = "high_rise" if height > 18.30 else "non_high_rise"
    env = compute_envelope(plot, bclass, plot.dwellings, height)
    env["inputs"] = plot.__dict__.copy()
    env["rule_source"] = env.get("rule", "TNCDBR-2019")
    # legacy field shapes used by the single-result view
    if env.get("allowed"):
        s = env["setbacks_m"]
        env["setbacks_m"] = {"front_m": s["front"], "side_each_m": s["side"],
                             "side_applies": s["side_applies"], "rear_m": s["rear"], "notes": []}
        m = env["max_built_up_area_sqm"]
        env["max_built_up_area_sqm"] = {"governing": m["governing"], "fsi_limit": m["fsi_limit"],
                                        "physical_limit_footprint_x_floors": m["physical_limit"],
                                        "max_floors_assumed": m["max_floors"]}
        env["fsi_max"] = env["fsi"]; env["assumed_height_m"] = height
        env["category"] = env["rule"]
    env["pending"] = [
        "OSR / reservation (Rule 41) - not yet extracted",
        "Premium FSI / TDR upside (Rules 48-49) - not yet applied",
        "Amendments (15 GOs) not yet layered",
    ]
    return env
