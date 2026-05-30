"""Branded, detailed PDF report generator (reportlab) for feasibility / compliance /
scrutiny. Renders the same data shown on screen — KPIs, height, FSI, setbacks,
obligations, parking, amendments — plus the actual plan + elevation diagrams
(SVGs sent from the browser, rasterised here via PyMuPDF)."""
from __future__ import annotations
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                HRFlowable, Image)

BRAND = colors.HexColor("#0f4c84")
GREEN = colors.HexColor("#1f9d5c")
RED = colors.HexColor("#d94d3a")
AMBER = colors.HexColor("#b97400")
LINE = colors.HexColor("#e2e8f0")
ALT = colors.HexColor("#f7fafd")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H", parent=ss["Title"], fontSize=18, textColor=BRAND, spaceAfter=2))
    ss.add(ParagraphStyle("Meta", parent=ss["Normal"], fontSize=9, textColor=colors.grey))
    ss.add(ParagraphStyle("Sec", parent=ss["Heading2"], fontSize=12, textColor=BRAND, spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], fontSize=9, leading=13))
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8, textColor=colors.grey, leading=11))
    return ss


def _svg_for_pdf(svg: str) -> str:
    """PyMuPDF's SVG renderer doesn't understand rgba()/opacity and treats unknown
    fills as black. Flatten every rgba(r,g,b,a) to a solid hex blended over white,
    and guarantee a white background rect so transparent areas don't render black."""
    import re

    def blend(m):
        r, g, b, a = float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))
        r = round(r * a + 255 * (1 - a)); g = round(g * a + 255 * (1 - a)); b = round(b * a + 255 * (1 - a))
        return f"#{r:02x}{g:02x}{b:02x}"

    s = re.sub(r"rgba\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)", blend, svg)
    # strip fill-opacity / opacity attrs fitz may mishandle
    s = re.sub(r'\s(fill|stroke)-opacity="[^"]*"', "", s)

    # thin strokes (1-2 px) drop out when fitz rasterises — floor every stroke-width
    # to >=1.6 so all borders (incl. thin vertical edges) survive.
    def bump(m):
        try:
            w = float(m.group(1))
        except ValueError:
            return m.group(0)
        return f'stroke-width="{max(w, 1.6)}"'
    s = re.sub(r'stroke-width="([\d.]+)"', bump, s)
    # white background: pull viewBox dims, inject a covering rect right after <svg ...>
    vb = re.search(r'viewBox="([\d.\-\s]+)"', s)
    if vb:
        p = vb.group(1).split()
        x, y, w, h = (p + ["0", "0", "800", "600"])[:4]
    else:
        x, y, w, h = "0", "0", "800", "600"
    if "data-pdfbg" not in s:
        bg = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#ffffff" data-pdfbg="1"/>'
        s = re.sub(r"(<svg\b[^>]*>)", r"\1" + bg, s, count=1)
    return s


def _svg_to_image(svg: str, max_w_mm: float, max_h_mm: float):
    """Rasterise an SVG string to a reportlab Image, scaled to fit a box (mm)."""
    if not svg or "<svg" not in svg:
        return None
    try:
        import fitz
        clean = _svg_for_pdf(svg)
        doc = fitz.open(stream=clean.encode("utf-8"), filetype="svg")
        pix = doc[0].get_pixmap(dpi=300, alpha=False)   # high DPI so thin strokes survive
        png = pix.tobytes("png")
        iw, ih = pix.width, pix.height
        scale = min((max_w_mm * mm) / iw, (max_h_mm * mm) / ih)
        return Image(io.BytesIO(png), width=iw * scale, height=ih * scale)
    except Exception:
        return None


def _kv_table(rows, col1=70 * mm, col2=95 * mm):
    ss = _styles()
    data = [[Paragraph(str(k), ss["Body"]), Paragraph(str(v), ss["Body"])] for k, v in rows]
    t = Table(data, colWidths=[col1, col2])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def _obligations_table(ob, ss):
    tag = {"mandatory": "MANDATORY", "applies": "APPLIES", "verify": "VERIFY"}
    data = [["Item", "Status", "Requirement", "Rule"]]
    items = ob.get("mandatory", []) + ob.get("applies", []) + ob.get("verify", [])
    for it in items:
        data.append([Paragraph(it["label"], ss["Small"]), tag.get(it["status"], ""),
                     Paragraph(it["text"], ss["Small"]), Paragraph(it["rule"], ss["Small"])])
    t = Table(data, colWidths=[28 * mm, 18 * mm, 80 * mm, 30 * mm])
    style = [("BACKGROUND", (0, 0), (-1, 0), BRAND), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
             ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ALT])]
    for i, it in enumerate(items, start=1):
        c = RED if it["status"] == "mandatory" else (BRAND if it["status"] == "applies" else AMBER)
        style.append(("TEXTCOLOR", (1, i), (1, i), c))
    t.setStyle(TableStyle(style))
    return t


def _checks_table(checks):
    data = [["Item", "Required", "Provided", "Status"]]
    for c in checks:
        u = c.get("unit", "m")
        req = f"{c['required']} {u}" if c.get("required") is not None else "—"
        prov = f"{c['proposed']} {u}" if c.get("proposed") is not None else "—"
        data.append([c["item"], req, prov, c["status"].replace("_", " ")])
    t = Table(data, colWidths=[70 * mm, 35 * mm, 35 * mm, 30 * mm])
    style = [("BACKGROUND", (0, 0), (-1, 0), BRAND), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ALT]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    for i, c in enumerate(checks, start=1):
        if c["status"] == "FAIL":
            style.append(("TEXTCOLOR", (3, i), (3, i), RED))
        elif c["status"] == "PASS":
            style.append(("TEXTCOLOR", (3, i), (3, i), GREEN))
    t.setStyle(TableStyle(style))
    return t


def _diagrams(result, ss):
    el = []
    dg = result.get("diagrams") or {}
    plan = _svg_to_image(dg.get("plan"), 82, 95)
    elev = _svg_to_image(dg.get("elevation"), 82, 95)
    if plan or elev:
        el.append(Spacer(1, 6))
        el.append(Paragraph("Plan & elevation", ss["Sec"]))
        cells = [[plan or Paragraph("—", ss["Small"]), elev or Paragraph("—", ss["Small"])],
                 [Paragraph("Plan — setbacks & buildable", ss["Small"]),
                  Paragraph("Elevation — height, floors & roof appurtenances", ss["Small"])]]
        t = Table(cells, colWidths=[88 * mm, 88 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        el.append(t)
    return el


def build_pdf(kind: str, meta: str, result: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=14 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm)
    ss = _styles()
    el = []
    titles = {"feasibility": "Feasibility Study", "compliance": "Compliance Check",
              "scrutiny": "Pre-DCR Scrutiny Report"}
    el.append(Paragraph("DCR — " + titles.get(kind, "Report"), ss["H"]))
    el.append(Paragraph("Tamil Nadu Combined Development & Building Rules, 2019 (with amendments)", ss["Meta"]))
    el.append(Paragraph(meta or "", ss["Meta"]))
    el.append(Spacer(1, 6))
    el.append(HRFlowable(width="100%", thickness=1.5, color=BRAND))

    if kind in ("compliance", "scrutiny"):
        verdict = result.get("verdict", "")
        col = GREEN if verdict == "COMPLIANT" else RED
        el.append(Spacer(1, 8))
        el.append(Paragraph(f'<font color="#{col.hexval()[2:]}"><b>{verdict}</b></font>'
                            + (f' — {result.get("deviation_count",0)} deviation(s)' if verdict != "COMPLIANT" else ""), ss["Sec"]))
        if result.get("rule"):
            el.append(Paragraph("Rule: " + str(result["rule"]), ss["Small"]))
        el.append(Spacer(1, 4))
        el.append(_checks_table(result.get("checks", [])))

        h = result.get("height")
        if h:
            el.append(Spacer(1, 6)); el.append(Paragraph("Height check", ss["Sec"]))
            el.append(_kv_table([
                ("Building height", f"{h['building_height_m']} m"),
                ("Ground rise above road", f"{h['ground_rise_m']} m"),
                ("Total height", f"{h['total_height_m']} m"),
                ("Permissible max", f"{h['max_height_m']} m"),
            ]))
            el.append(Paragraph(h.get("note", ""), ss["Small"]))
        st = result.get("stilt")
        if st:
            el.append(Spacer(1, 6)); el.append(Paragraph("Stilt / FSI treatment", ss["Sec"]))
            el.append(_kv_table([
                ("Stilt parking area", f"{st['area_sqm']} m²"),
                ("Counts in FSI?", "Yes (enclosed)" if st["counts_in_fsi"] else "No (open parking)"),
                ("FSI-countable built-up", f"{st['countable_bua_sqm']} m²"),
                ("FSI used / max", f"{st.get('fsi_used')} / {st.get('fsi_max')}"),
                ("Basis", st.get("rule", "")),
            ]))
        ad = result.get("auto_derived")
        if ad:
            sb = ad["setbacks_m"]
            el.append(Paragraph(f"Auto-derived from drawing: plot {ad['plot_area_sqm']} m² · footprint {ad['footprint_sqm']} m² "
                                f"({ad['coverage_pct']}% cover) · built-up {ad['built_up_sqm']} m² · {ad['floors']} floors · "
                                f"setbacks F{sb['front']}/S{sb['side']}/R{sb['rear']} m", ss["Small"]))
        ob = result.get("obligations")
        if ob and ob.get("count"):
            el.append(Spacer(1, 6)); el.append(Paragraph("Mandatory provisions & approvals", ss["Sec"]))
            el.append(_obligations_table(ob, ss))
        el += _diagrams(result, ss)

    elif kind == "feasibility":
        el.append(Spacer(1, 6))
        el.append(Paragraph("Recommended: <b>%s</b>" % result.get("recommended", "—"), ss["Sec"]))
        data = [["Option", "Achievable", "FSI permits", "FSI", "Floors", "Units", "Cars", "Feasible"]]
        for s in result.get("scenarios", []):
            if s.get("feasible"):
                data.append([s["scenario"], f"{s['max_built_up_sqm']} m²",
                             f"{s.get('fsi_permissible_sqm','-')} m²", str(s["fsi"]), str(s["floors"]),
                             str(s.get("est_dwelling_units") or "—"), str(s["parking"]["car_spaces"]), "Yes"])
            else:
                data.append([s["scenario"], "—", "—", "—", "—", "—", "—", "No: " + s.get("reason", "")[:26]])
        t = Table(data, colWidths=[44 * mm, 22 * mm, 22 * mm, 10 * mm, 12 * mm, 12 * mm, 10 * mm, 26 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BRAND), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ALT])]))
        el.append(t)

        scs = result.get("scenarios", [])
        rec = next((s for s in scs if s.get("scenario") == result.get("recommended") and s.get("feasible")), None)
        rec = rec or next((s for s in scs if s.get("feasible")), None)
        if rec:
            el.append(Spacer(1, 8))
            el.append(Paragraph("Selected option — %s" % rec["scenario"], ss["Sec"]))
            sb = rec.get("setbacks_m", {})
            kv = [
                ("FSI permissible (plot × FSI)", f"{rec.get('fsi_permissible_sqm')} m²"),
                ("Achievable built-up", f"{rec.get('max_built_up_sqm')} m² in {rec.get('floors')} floor(s)"
                                        + (f" (bound by {rec['bound_by']})" if rec.get("bound_by") else "")),
                ("Footprint / coverage", f"{rec.get('footprint_sqm')} m² · {rec.get('coverage_pct')}%"),
                ("Setbacks F/S/R", f"{sb.get('front')}/{sb.get('side')}/{sb.get('rear')} m"),
                ("Parking", f"{rec['parking']['car_spaces']} car · {rec['parking']['two_wheeler_spaces']} TW"),
            ]
            ev = rec.get("elevation", {})
            if ev:
                kv.append(("Permissible height", f"{ev.get('max_height_m')} m (to terrace parapet; "
                                                 f"lift room/tank not counted, Rule 35 Expl.2(iii))"))
            pr = rec.get("premium_fsi", {})
            if pr.get("premium_pct"):
                kv.append(("Premium FSI (Rule 49)", f"+{pr['premium_pct']}% = {pr['upside_sqm']} m²"))
            osr = rec.get("osr", {})
            kv.append(("OSR (Rule 41)", f"{osr['required_sqm']} m² ({osr.get('pct')}%)" if osr.get("required_sqm") else "Nil"))
            el.append(_kv_table(kv))

            ob = rec.get("obligations")
            if ob and ob.get("count"):
                el.append(Spacer(1, 6)); el.append(Paragraph("Mandatory provisions & approvals", ss["Sec"]))
                el.append(_obligations_table(ob, ss))
                el.append(Paragraph("“Verify” items depend on the site / master-plan and must be confirmed with the "
                                    "sanctioning authority — not auto-computed.", ss["Small"]))
        el += _diagrams(result, ss)

        site = result.get("site_notes") or []
        if site:
            el.append(Spacer(1, 6)); el.append(Paragraph("Site notes", ss["Sec"]))
            for n in site:
                el.append(Paragraph("• " + n, ss["Small"]))
        am = result.get("amendments", {})
        if am:
            el.append(Spacer(1, 6))
            el.append(Paragraph(f"Amendments reviewed through {am.get('reviewed_through','')} · "
                                f"{am.get('reviewed')}/{am.get('total')} GOs.", ss["Small"]))

    el.append(Spacer(1, 10))
    el.append(HRFlowable(width="100%", thickness=0.5, color=LINE))
    el.append(Paragraph("Indicative report per TNCDBR-2019. Verify with the sanctioning authority before submission.", ss["Small"]))
    doc.build(el)
    return buf.getvalue()
