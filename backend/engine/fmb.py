"""FMB sketch helper: render an uploaded FMB PDF to an image for on-screen display,
and attempt to pull header text (survey no, village, area) if a text layer exists.

Many TN FMB PDFs have NO text layer (the sample does not) -- in that case the user
reads the labelled edge dimensions off the rendered image and types them in.
Automatic dimension OCR is a planned later enhancement.
"""
from __future__ import annotations
import base64, io, re
import fitz


def render_and_probe(pdf_bytes: bytes) -> dict:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    # render to PNG at 2x for a crisp preview
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    png_b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
    text = page.get_text("text") or ""
    doc.close()

    parsed = {"survey_no": None, "village": None, "district": None,
              "taluk": None, "area_sqm": None, "has_text_layer": len(text) > 50}

    def grab(label):
        m = re.search(label + r"\s*[:：]\s*([^\n]+)", text, re.I)
        return m.group(1).strip() if m else None

    parsed["survey_no"] = grab("Survey No")
    parsed["village"] = grab("Village")
    parsed["district"] = grab("District")
    parsed["taluk"] = grab("Taluk")
    # Area like "Hect 00 Ares 2 Sqm 18"
    am = re.search(r"Hect\s*(\d+)\s*Ares\s*(\d+)\s*Sqm\s*(\d+)", text, re.I)
    if am:
        h, a, s = map(int, am.groups())
        parsed["area_sqm"] = h * 10000 + a * 100 + s

    return {"preview_png_b64": png_b64, "parsed": parsed}
