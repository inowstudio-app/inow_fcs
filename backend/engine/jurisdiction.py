"""
District -> jurisdiction & planning context.

TN building rules (setbacks/FSI/coverage) are statewide under TNCDBR-2019; what varies
by location is the planning AUTHORITY (CMDA inside the Chennai Metropolitan Area vs DTCP
elsewhere), the master-plan land-use ZONE, and overlays (CRZ on the coast). This maps a
district to that context and produces advisory notes — it does NOT change the numeric rules.
"""
from __future__ import annotations

CMA_FULL = {"Chennai"}
CMA_PARTIAL = {"Tiruvallur", "Kancheepuram", "Chengalpattu"}  # partly inside Chennai Metro Area
COASTAL = {"Chennai", "Tiruvallur", "Chengalpattu", "Kancheepuram", "Cuddalore", "Mayiladuthurai",
           "Nagapattinam", "Tiruvarur", "Thanjavur", "Pudukkottai", "Ramanathapuram",
           "Thoothukudi", "Tirunelveli", "Tenkasi", "Kanniyakumari"}


def jurisdiction(district: str | None) -> dict | None:
    if not district:
        return None
    notes = []
    if district in CMA_FULL:
        authority, region = "CMDA", "Chennai Metropolitan Area"
        notes.append("Chennai Metropolitan Development Authority (CMDA) jurisdiction — Second Master Plan applies.")
        suggest = "cmda"
    elif district in CMA_PARTIAL:
        authority, region = "CMDA / DTCP", "Partly within Chennai Metro Area"
        notes.append(f"{district} partly falls within the Chennai Metropolitan Area: CMDA applies inside the CMA "
                     "boundary, DTCP / local body outside. Confirm which side of the CMA boundary the plot is on.")
        suggest = None
    else:
        authority, region = "DTCP", "DTCP (outside Chennai Metro Area)"
        notes.append("DTCP / local body jurisdiction (outside Chennai Metro Area) — the local body master plan + "
                     "TNCDBR-2019 apply.")
        suggest = None
    if district in COASTAL:
        notes.append("Coastal district: if the plot is within 500 m of the High Tide Line, CRZ clearance may be "
                     "required (verify on the CRZ map) — it can restrict or prohibit construction.")
    notes.append("Building rules (setbacks, FSI, coverage) are statewide under TNCDBR-2019; the district determines "
                 "jurisdiction and the master-plan land-use zone, not different setback/FSI numbers.")
    return {"district": district, "authority": authority, "region": region,
            "suggest_authority": suggest, "notes": notes}
