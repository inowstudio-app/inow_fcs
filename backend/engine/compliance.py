"""
Compliance check: compare a PROPOSED design against the permissible envelope and
flag deviations. This is the reverse direction of feasibility, sharing the same engine.
"""
from __future__ import annotations
from dataclasses import dataclass

from .feasibility import Plot, compute_envelope


@dataclass
class Proposal:
    height_m: float
    dwellings: int = 1
    front_setback_m: float | None = None
    side_setback_m: float | None = None
    rear_setback_m: float | None = None
    built_up_area_sqm: float | None = None
    footprint_area_sqm: float | None = None
    car_parking_provided: int | None = None
    stilt_area_sqm: float | None = None      # open stilt parking area at GF (Rule 29(5))
    stilt_enclosed: bool = False             # if enclosed, stilt counts toward FSI (Rule 35.10)
    ground_rise_m: float = 0.0               # plinth / ground level raised above road level


def _check(label, proposed, required, kind="min", unit="m"):
    """kind='min': proposed must be >= required; kind='max': proposed must be <= required."""
    if proposed is None:
        return {"item": label, "status": "not_provided", "required": required, "proposed": None}
    ok = proposed >= required - 1e-6 if kind == "min" else proposed <= required + 1e-6
    return {"item": label, "status": "PASS" if ok else "FAIL",
            "required": round(required, 2), "proposed": round(proposed, 2), "unit": unit,
            "rule": f"{'min' if kind == 'min' else 'max'} {round(required,2)} {unit}"}


def check_compliance(plot: Plot, prop: Proposal) -> dict:
    bclass = "high_rise" if prop.height_m > 18.30 else "non_high_rise"
    env = compute_envelope(plot, bclass, prop.dwellings, prop.height_m)
    if not env.get("allowed"):
        return {"buildable": False, "reason": env.get("reason"), "checks": []}

    sb = env["setbacks_m"]
    maxbua = env["max_built_up_area_sqm"]["governing"]
    fsi = env["fsi"]
    plot_area = plot.area_sqm
    maxcov = env["buildable_footprint"]["area_sqm"]
    req_parking = env["parking"]["car_spaces"]
    max_height = env["elevation"]["max_height_m"]

    # --- Stilt / FSI treatment (Rule 29(5) open stilt excluded; Rule 35.10 enclosed counts) ---
    stilt = round(prop.stilt_area_sqm or 0.0, 2)
    gross = prop.built_up_area_sqm                       # total built-up the user enters
    stilt_info = None
    countable_bua = gross
    if gross is not None and stilt > 0:
        if prop.stilt_enclosed:
            countable_bua = gross                        # enclosed stilt already counts
            rule = "Rule 35 sub-cl.10 (enclosed stilt counts in FSI)"
            counts = True
        else:
            countable_bua = max(0.0, gross - stilt)      # open stilt excluded
            rule = "Rule 29(5) (open stilt parking excluded from FSI)"
            counts = False
        stilt_info = {"area_sqm": stilt, "counts_in_fsi": counts,
                      "countable_bua_sqm": round(countable_bua, 2),
                      "fsi_used": round(countable_bua / plot_area, 3) if plot_area else None,
                      "fsi_max": fsi, "rule": rule}

    # --- Total height incl. ground/plinth rise above road, vs regulated max ---
    rise = round(prop.ground_rise_m or 0.0, 2)
    total_height = round(prop.height_m + rise, 2)
    height_info = {"building_height_m": prop.height_m, "ground_rise_m": rise,
                   "total_height_m": total_height, "max_height_m": max_height,
                   "note": "Height measured from road level; plinth/ground rise added (Rule 2 height defn)."}

    checks = [
        _check("Front setback", prop.front_setback_m, sb["front"], "min"),
        _check("Side setback", prop.side_setback_m, sb["side"], "min"),
        _check("Rear setback", prop.rear_setback_m, sb["rear"], "min"),
        _check("Building height (incl. ground rise)", total_height, max_height, "max"),
        _check("Built-up area (FSI-countable)", countable_bua, maxbua, "max", "m²"),
        _check("Ground coverage (footprint)", prop.footprint_area_sqm, maxcov, "max", "m²"),
        _check("Car parking", prop.car_parking_provided, req_parking, "min", "spaces"),
    ]
    fails = [c for c in checks if c["status"] == "FAIL"]
    return {
        "buildable": True, "building_class": bclass, "rule": env["rule"],
        "verdict": "COMPLIANT" if not fails else "NON-COMPLIANT",
        "deviation_count": len(fails),
        "permissible": {"fsi": fsi, "max_built_up_sqm": maxbua,
                        "setbacks_m": sb, "max_footprint_sqm": maxcov, "car_parking": req_parking,
                        "max_height_m": max_height},
        "stilt": stilt_info,
        "height": height_info,
        "obligations": env.get("obligations"),
        "elevation": env.get("elevation"),
        "checks": checks,
        "note": "Indicative; based on rules extracted so far. Amendments not yet layered.",
    }
