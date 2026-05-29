"""
Amendment layering. Loads the date-ordered amendment catalogue and exposes:
- status(): provenance summary for the report (reviewed-through date, applied/pending).
- single_dwelling_parking_cap(): GO 156/2025 cap.
- advisories(use, built_up_sqm, dwellings): GO 155 & 171 advisory notes that apply.
Numeric rule overrides are applied where extracted; un-reviewed scanned GOs are flagged.
"""
from __future__ import annotations
import json, os

AMEND_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "rules", "amendments", "index.json")


def _load():
    with open(AMEND_PATH, encoding="utf-8") as f:
        return json.load(f)


def status() -> dict:
    a = _load()
    reviewed = [x for x in a["amendments"] if x["status"] == "reviewed"]
    pending = [x["go"] for x in a["amendments"] if x["status"] == "needs_review"]
    applied_types = ("parking_cap", "rule35_height")
    applied = [f"GO {x['go']} ({x['date']})" for x in reviewed
               if any(o.get("type", "").startswith(applied_types) for o in x.get("engine_overrides", []))]
    return {
        "reviewed_through": a["reviewed_through"],
        "total": len(a["amendments"]), "reviewed": len(reviewed), "pending_review": pending,
        "numeric_overrides_applied": applied,
        "note": "All 15 amendment GOs reviewed. Applied to engine: GO 69/2024 (NHR height 12m->14m) & GO 156/2025 (single-dwelling parking cap). "
                "Setback/FSI/OSR%/coverage otherwise verified unchanged; metro-corridor Premium-FSI concessions (GO 15/152) are charge-only (CMA)."
                + (f" PENDING: {', '.join(pending)}." if pending else ""),
    }


def single_dwelling_parking_cap(built_up_sqm: float) -> dict | None:
    """GO 156/2025: single dwelling house parking cap."""
    for x in _load()["amendments"]:
        for o in x.get("engine_overrides", []):
            if o.get("type") == "parking_cap_single_dwelling":
                band = o["upto_300sqm"] if built_up_sqm <= 300 else o["above_300sqm"]
                return {"car": band["car"], "tw": band["tw"], "source": f"GO {x['go']}/{x['date'][:4]}"}
    return None


def advisories(use: str, built_up_sqm: float, dwellings: int) -> list[str]:
    out = []
    for x in _load()["amendments"]:
        for o in x.get("engine_overrides", []):
            if o.get("type") != "advisory":
                continue
            cond = o.get("applies_when", "")
            hit = ((cond == "built_up_sqm>750" and built_up_sqm > 750)
                   or (cond == "dwellings>50" and dwellings > 50)
                   or (cond == "use!=residential and built_up_sqm>300" and use != "residential" and built_up_sqm > 300))
            if hit:
                out.append(o["note"])
    return out
