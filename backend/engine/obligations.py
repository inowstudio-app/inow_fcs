"""Mandatory provisions, approvals & eligibility checklist for a feasibility option.

These are the items a feasibility report must FLAG even though the core engine
(setbacks/FSI/parking) doesn't compute them numerically — rainwater harvesting,
lift, fire NOC, solar, STP, EWS reservation, land-use verification, road-line
check, and minimum plot/road eligibility. Each item is honest about whether it is
a hard requirement, conditionally required, or a 'verify with authority' advisory,
and cites the governing rule. No fabricated numeric limits — thresholds used are
the ones defensible from TNCDBR-2019; everything else is phrased as 'verify'.
"""
from __future__ import annotations

# status: "mandatory" (always), "applies" (triggered for this design),
#         "verify" (must be checked against site/master-plan; we can't compute it)


def eligibility(building_class: str, plot_area: float, road_width: float,
                dwellings: int, height: float) -> dict:
    """Hard-ish eligibility gate. Returns {ok, reasons[]} — reasons block the option.
    Only uses thresholds defensible from the rules; otherwise stays silent."""
    reasons = []
    if building_class == "high_rise":
        if road_width < 12.0:
            reasons.append(f"High-rise (Rule 39) needs an abutting road ≥ 12 m; have {road_width:.1f} m.")
    else:
        # Rule 35.1.b (>16 dwellings) requires road >= 9 m
        if dwellings > 16 and road_width < 9.0:
            reasons.append(f"More than 16 dwellings (Rule 35.1.b) needs road ≥ 9 m; have {road_width:.1f} m.")
        # other-areas minimum access road (Rule 35.1.a)
        if road_width < 3.0:
            reasons.append(f"Minimum access road for development is ~3 m; have {road_width:.1f} m (Rule 35).")
    return {"ok": not reasons, "reasons": reasons}


def checklist(use: str, building_class: str, plot_area: float, road_width: float,
              dwellings: int, height: float, floors: int, bua: float,
              has_stilt: bool = False) -> list:
    """Return a list of obligation items for this development option."""
    items = []

    def add(key, label, status, text, rule):
        items.append({"key": key, "label": label, "status": status, "text": text, "rule": rule})

    # --- Land use / zoning (cannot compute — no statewide zoning data) ---
    add("land_use", "Land-use zone", "verify",
        "Confirm the proposed use is permitted in the plot's master-plan / detailed-development land-use zone "
        "(Residential / Commercial / Mixed / etc.). Use is decisive and overrides this study if disallowed.",
        "TNCDBR-2019 Rule 16 & use-zone schedules")

    # --- Road line / widening ---
    add("road_line", "Road line / widening", "verify",
        "Check the road against any proposed widening / building-line in the Master Plan or with Highways/local body. "
        "Land within a road-widening line is surrendered and reduces the buildable plot.",
        "TNCDBR-2019 Rule 18 (road widths)")

    # --- Rainwater harvesting (always mandatory in TN) ---
    rwh = max(1, round(plot_area * 0.0))  # placeholder to keep type; sizing below is text
    add("rwh", "Rainwater harvesting", "mandatory",
        "RWH structures are mandatory for every building (recharge wells / percolation pits sized to roof + paved "
        "area). Provide and show on the plan; required for completion certificate.",
        "TNCDBR-2019 Rule 63 / Annexure XXII")

    # --- Lift ---
    lift_needed = floors >= 4 or height > 15.0
    add("lift", "Lift / elevator",
        "applies" if lift_needed else "verify",
        ("A passenger lift is required (building exceeds ~G+3 / 15 m). Provide a lift; its machine-room/well "
         "is FSI/height-exempt as a service structure."
         if lift_needed else
         "A lift is not triggered at this height, but provide one if any floor is > 15 m or for accessibility."),
        "TNCDBR-2019 Rule 43 (accessibility) & NBC")

    # --- Fire & life safety / NOC ---
    if building_class == "high_rise" or height > 18.3:
        add("fire", "Fire service NOC", "applies",
            "High-rise buildings require Tamil Nadu Fire & Rescue Services NOC and full fire provisions "
            "(2 staircases, fire lift, refuge area, fire tank, setback for fire tender movement).",
            "TNCDBR-2019 Rule 64 + TNFRS")
    else:
        add("fire", "Fire & life safety", "applies" if floors >= 3 else "verify",
            "Provide exits/staircase width, travel distance and a fire tank per occupancy. Assembly, institutional, "
            "hospital and commercial uses need a Fire NOC even when non-high-rise.",
            "TNCDBR-2019 Rule 53 (exits) & 64 (fire safety)")

    # --- Solar (water heating + PV) ---
    add("solar", "Solar water heating / PV", "applies" if (plot_area >= 100 or bua >= 200) else "verify",
        "Provide solar water heating and roof-top solar PV provision per occupancy and plot size; "
        "required for plan sanction in most local bodies.",
        "TNCDBR-2019 Rule 44 (solar)")

    # --- Sewage / STP ---
    big = dwellings >= 20 or bua >= 2000
    add("stp", "Sewage disposal / STP", "applies" if big else "verify",
        ("A sewage treatment plant (STP) is required for large developments; provide and show treated-water reuse."
         if big else
         "Connect to the public sewer; where absent, provide a septic tank / soak pit or STP as the local body requires."),
        "TNCDBR-2019 Part VII (drainage) & TNPCB")

    # --- EWS / shelter (large residential) ---
    if use == "residential" and (dwellings >= 8 or bua >= 2000):
        add("ews", "EWS / shelter obligation", "applies",
            "Large residential developments must reserve EWS housing or pay shelter charges as required by the "
            "sanctioning authority.",
            "TNCDBR-2019 Rule 34 (shelter charges)")

    # --- OSR reminder for layouts/large plots handled elsewhere (Rule 41) ---

    # --- Stilt parking (only when chosen) ---
    if has_stilt:
        add("stilt", "Stilt parking floor", "applies",
            "An OPEN stilt floor used only for parking is exempt from FSI and is not counted in building height "
            "(if it stays open on all sides and within the permitted stilt height). Enclosing it makes it count.",
            "TNCDBR-2019 Rule 29 (FSI exclusions) & Rule 35 sub-cl.10")

    return items


def summarize(items: list) -> dict:
    return {
        "mandatory": [i for i in items if i["status"] == "mandatory"],
        "applies": [i for i in items if i["status"] == "applies"],
        "verify": [i for i in items if i["status"] == "verify"],
        "count": len(items),
    }
