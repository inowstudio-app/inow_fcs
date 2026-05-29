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
    maxcov = env["buildable_footprint"]["area_sqm"]
    req_parking = env["parking"]["car_spaces"]

    checks = [
        _check("Front setback", prop.front_setback_m, sb["front"], "min"),
        _check("Side setback", prop.side_setback_m, sb["side"], "min"),
        _check("Rear setback", prop.rear_setback_m, sb["rear"], "min"),
        _check("Built-up area (FSI)", prop.built_up_area_sqm, maxbua, "max", "m²"),
        _check("Ground coverage (footprint)", prop.footprint_area_sqm, maxcov, "max", "m²"),
        _check("Car parking", prop.car_parking_provided, req_parking, "min", "spaces"),
    ]
    fails = [c for c in checks if c["status"] == "FAIL"]
    return {
        "buildable": True, "building_class": bclass, "rule": env["rule"],
        "verdict": "COMPLIANT" if not fails else "NON-COMPLIANT",
        "deviation_count": len(fails),
        "permissible": {"fsi": env["fsi"], "max_built_up_sqm": maxbua,
                        "setbacks_m": sb, "max_footprint_sqm": maxcov, "car_parking": req_parking},
        "checks": checks,
        "note": "Indicative; based on rules extracted so far. Amendments not yet layered.",
    }
