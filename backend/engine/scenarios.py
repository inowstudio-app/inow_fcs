"""
"Highest & best use" scenario engine.
Given a plot, evaluate candidate development types and rank the feasible ones by yield.
This is what turns the tool from a calculator into an advisor for the architect.
"""
from __future__ import annotations
import math
from dataclasses import replace

from .feasibility import Plot, compute_envelope
from .parking import estimate_parking
from . import amendments
from .jurisdiction import jurisdiction

AVG_UNIT_SQM = 70.0  # assumption for estimating dwelling yield; surfaced in output


def _units_from_bua(bua: float) -> int:
    return max(1, int(bua // AVG_UNIT_SQM))


def run_scenarios(plot: Plot) -> dict:
    candidates = [
        ("Single residence", "non_high_rise", "residential", 1, 11.0),
        ("Multi-dwelling (≤16, mid-rise)", "non_high_rise", "residential", 16, 11.0),
        ("Apartments (non-high-rise, ≤18.3m)", "non_high_rise", "residential", 24, 18.30),
        ("High-rise apartments", "high_rise", "residential", 80, 30.0),
        ("Commercial block", "non_high_rise", "commercial", 1, 11.0),
    ]
    results = []
    for name, bclass, use, dwellings, height in candidates:
        p = replace(plot, use=use, dwellings=dwellings, proposed_height_m=height)
        env = compute_envelope(p, bclass, dwellings, height)
        row = {"scenario": name, "use": use, "building_class": bclass, "intended_height_m": height}
        if not env.get("allowed"):
            row.update({"feasible": False, "reason": env.get("reason", "not permissible")})
        else:
            bua = env["max_built_up_area_sqm"]["governing"]
            # clamp BUA-based unit estimate to the candidate's dwelling count
            est_units = min(dwellings, _units_from_bua(bua)) if use == "residential" else None
            # parking based on the estimated yield so BUA/units/parking stay coherent
            parking = (estimate_parking(use, bua, est_units, plot.parking_area_class)
                       if use == "residential" else env["parking"])
            row.update({
                "feasible": True, "rule": env["rule"], "fsi": env["fsi"],
                "max_built_up_sqm": bua,
                "footprint_sqm": env["buildable_footprint"]["area_sqm"],
                "coverage_pct": env["buildable_footprint"]["coverage_pct"],
                "floors": env["max_built_up_area_sqm"]["max_floors"],
                "setbacks_m": env["setbacks_m"],
                "geometry": env["geometry"],
                "est_dwelling_units": est_units,
                "parking": parking,
                "osr": env["osr"],
                "premium_fsi": env["premium_fsi"],
                "advisories": env.get("advisories", []),
            })
        results.append(row)

    feasible = [r for r in results if r["feasible"]]
    recommended = max(feasible, key=lambda r: r["max_built_up_sqm"])["scenario"] if feasible else None

    site_notes = []
    rs = plot.road_sides or {}
    if len([w for w in rs.values() if w]) > 1:
        widest = max(rs.items(), key=lambda kv: kv[1] or 0)
        site_notes.append(f"Corner/multi-road plot: front setback taken from the widest road ({widest[0]} side, "
                          f"{widest[1]} m); other road sides take side/rear setback (Rule 35 Expl.2(iv)).")
    if plot.plot_type == "gated":
        site_notes.append("Gated / approved-layout plot: roads & OSR are handled at the layout level; "
                          "individual-plot setbacks per Rule 35 still apply unless the sanctioned layout specifies otherwise.")
    juris = jurisdiction(plot.district)
    if juris:
        site_notes = juris["notes"] + site_notes
    return {
        "plot": {"area_sqm": plot.area_sqm, "width_m": plot.width_m, "depth_m": plot.depth_m,
                 "abutting_road_width_m": plot.abutting_road_width_m, "survey_no": plot.survey_no},
        "scenarios": results,
        "recommended": recommended,
        "assumptions": {"avg_dwelling_unit_sqm": AVG_UNIT_SQM},
        "site_notes": site_notes,
        "jurisdiction": juris,
        "amendments": amendments.status(),
        "pending": ["Use-zone schedules", "Rule 47 layout/sub-division",
                    "Older scanned amendments pending OCR: " + (", ".join(amendments.status()["pending_review"]) or "none")],
    }
