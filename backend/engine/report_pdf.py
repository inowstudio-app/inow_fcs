"""Branded PDF report generator (reportlab). Renders feasibility / compliance / scrutiny
results into a client-ready PDF."""
from __future__ import annotations
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable)

BRAND = colors.HexColor("#0f4c84")
GREEN = colors.HexColor("#1f9d5c")
RED = colors.HexColor("#d94d3a")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H", parent=ss["Title"], fontSize=18, textColor=BRAND, spaceAfter=2))
    ss.add(ParagraphStyle("Meta", parent=ss["Normal"], fontSize=9, textColor=colors.grey))
    ss.add(ParagraphStyle("Sec", parent=ss["Heading2"], fontSize=12, textColor=BRAND, spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8, textColor=colors.grey))
    return ss


def _checks_table(checks):
    data = [["Item", "Required", "Provided", "Status"]]
    for c in checks:
        u = c.get("unit", "m")
        req = f"{c['required']} {u}" if c.get("required") is not None else "—"
        prov = f"{c['proposed']} {u}" if c.get("proposed") is not None else "—"
        data.append([c["item"], req, prov, c["status"].replace("_", " ")])
    t = Table(data, colWidths=[70 * mm, 35 * mm, 35 * mm, 30 * mm])
    style = [("BACKGROUND", (0, 0), (-1, 0), BRAND), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafd")]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    for i, c in enumerate(checks, start=1):
        if c["status"] == "FAIL":
            style.append(("TEXTCOLOR", (3, i), (3, i), RED))
        elif c["status"] == "PASS":
            style.append(("TEXTCOLOR", (3, i), (3, i), GREEN))
    t.setStyle(TableStyle(style))
    return t


def build_pdf(kind: str, meta: str, result: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm)
    ss = _styles()
    el = []
    titles = {"feasibility": "Feasibility Study", "compliance": "Compliance Check", "scrutiny": "Pre-DCR Scrutiny Report"}
    el.append(Paragraph("DCR — " + titles.get(kind, "Report"), ss["H"]))
    el.append(Paragraph("Tamil Nadu Combined Development & Building Rules, 2019", ss["Meta"]))
    el.append(Paragraph(meta or "", ss["Meta"]))
    el.append(Spacer(1, 6))
    el.append(HRFlowable(width="100%", thickness=1.5, color=BRAND))

    if kind in ("compliance", "scrutiny"):
        verdict = result.get("verdict", "")
        col = GREEN if verdict == "COMPLIANT" else RED
        el.append(Spacer(1, 8))
        el.append(Paragraph(f'<font color="#{col.hexval()[2:]}"><b>{verdict}</b></font>'
                            + (f' — {result.get("deviation_count",0)} deviation(s)' if verdict != "COMPLIANT" else ""), ss["Sec"]))
        ad = result.get("auto_derived")
        if ad:
            sb = ad["setbacks_m"]
            el.append(Paragraph(f"Auto-derived from drawing: plot {ad['plot_area_sqm']} m² · footprint {ad['footprint_sqm']} m² "
                                f"({ad['coverage_pct']}% cover) · built-up {ad['built_up_sqm']} m² · {ad['floors']} floors · "
                                f"setbacks F{sb['front']}/S{sb['side']}/R{sb['rear']} m", ss["Small"]))
        el.append(Spacer(1, 4))
        el.append(_checks_table(result.get("checks", [])))
        el.append(Paragraph("Rule: " + str(result.get("rule", "")), ss["Small"]))
    elif kind == "feasibility":
        el.append(Spacer(1, 6))
        el.append(Paragraph("Recommended: <b>%s</b>" % result.get("recommended", "—"), ss["Sec"]))
        data = [["Option", "Max built-up", "FSI", "Floors", "Units", "Cars", "Feasible"]]
        for s in result.get("scenarios", []):
            if s.get("feasible"):
                data.append([s["scenario"], f"{s['max_built_up_sqm']} m²", str(s["fsi"]), str(s["floors"]),
                             str(s.get("est_dwelling_units") or "—"), str(s["parking"]["car_spaces"]), "Yes"])
            else:
                data.append([s["scenario"], "—", "—", "—", "—", "—", "No: " + s.get("reason", "")[:30]])
        t = Table(data, colWidths=[52 * mm, 26 * mm, 12 * mm, 14 * mm, 14 * mm, 12 * mm, 30 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BRAND), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafd")])]))
        el.append(t)
        am = result.get("amendments", {})
        if am:
            el.append(Spacer(1, 6))
            el.append(Paragraph(f"Amendments reviewed through {am.get('reviewed_through','')} · {am.get('reviewed')}/{am.get('total')} GOs.", ss["Small"]))

    el.append(Spacer(1, 10))
    el.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    el.append(Paragraph("Indicative report per TNCDBR-2019. Verify with the sanctioning authority before submission.", ss["Small"]))
    doc.build(el)
    return buf.getvalue()
