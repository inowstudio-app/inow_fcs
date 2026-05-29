"""Parking estimator per Annexure IV. Returns car + two-wheeler counts (estimate)."""
from __future__ import annotations
import json, math, os

RULES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "rules")


def _load():
    with open(os.path.join(RULES_DIR, "annexure_iv_parking.json"), encoding="utf-8") as f:
        return json.load(f)


def estimate_parking(use: str, built_up_sqm: float, dwellings: int, area_class: str = "corporation_municipal") -> dict:
    a = _load()
    cars = tw = 0.0
    basis = ""
    if use == "residential":
        per_unit = built_up_sqm / max(dwellings, 1)
        bands = a["residential"].get(area_class, a["residential"]["corporation_municipal"])
        band = next((b for b in bands if b.get("floor_area_upto_sqm") is None or per_unit <= b["floor_area_upto_sqm"]), bands[-1])
        if band.get("rule") == "nil":
            basis = "exempt (small units)"
        elif "car_per_floor_area_sqm" in band:
            cars = built_up_sqm / band["car_per_floor_area_sqm"]
            tw = dwellings
            basis = f"1 car / {band['car_per_floor_area_sqm']} sqm"
        elif "car_per_n_dwellings" in band:
            cars = dwellings / band["car_per_n_dwellings"]
            tw = dwellings * band.get("two_wheeler_per_dwelling", 1)
            basis = f"1 car / {band['car_per_n_dwellings']} dwellings"
        else:  # two-wheeler-only band (small units)
            tw = dwellings * band.get("two_wheeler", 1)
            basis = "two-wheeler only (small units)"
        if dwellings > 6:
            cars += a["visitor_parking_pct"] / 100 * cars  # visitor add-on
            basis += " + 10% visitor"
    elif use == "commercial":
        c = a["shops_commercial"].get(area_class, a["shops_commercial"]["corporation_municipal"])
        chargeable = max(0.0, built_up_sqm - c["exempt_first_sqm"])
        cars = chargeable / c["car_and_tw_per_sqm"]
        tw = chargeable / c["car_and_tw_per_sqm"]
        basis = f"1 car+1 TW / {c['car_and_tw_per_sqm']} sqm (first {c['exempt_first_sqm']} sqm exempt)"
    else:
        basis = "use not modelled"

    car_spaces, tw_spaces = math.ceil(cars), math.ceil(tw)
    amend_note = None
    # GO 156/2025: cap parking for a single dwelling house
    if use == "residential" and dwellings == 1:
        from .amendments import single_dwelling_parking_cap
        cap = single_dwelling_parking_cap(built_up_sqm)
        if cap:
            if car_spaces > cap["car"] or tw_spaces > cap["tw"]:
                amend_note = f"Capped to {cap['car']} car / {cap['tw']} TW for a single dwelling ({cap['source']})."
            car_spaces, tw_spaces = min(car_spaces, cap["car"]), min(tw_spaces, cap["tw"])

    return {
        "car_spaces": car_spaces,
        "two_wheeler_spaces": tw_spaces,
        "basis": basis,
        "source": "Annexure IV",
        "note": "Estimate; exact count depends on per-unit floor areas." + (" " + amend_note if amend_note else ""),
    }
