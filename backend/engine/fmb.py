"""
FMB sketch extraction. Renders the FMB PDF to an image, OCRs it (RapidOCR), and pulls
cadastral fields + plot dimensions. Reports which fields were detected and which are
missing (so the UI can flag them for manual entry).

Falls back gracefully to PDF text-layer extraction if OCR is unavailable.
"""
from __future__ import annotations
import base64, io, re
import fitz

_OCR = None  # lazy singleton (model load is slow)


def _get_ocr():
    global _OCR
    if _OCR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR = RapidOCR()
        except Exception:
            _OCR = False  # mark unavailable
    return _OCR


def _ocr_lines(pix) -> list[str]:
    ocr = _get_ocr()
    if not ocr:
        return []
    import numpy as np
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3]
    res, _ = ocr(img)
    return [txt for (_box, txt, _conf) in (res or [])]


def render_and_probe(pdf_bytes: bytes) -> dict:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
    png_b64 = base64.b64encode(page.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")).decode("ascii")

    # text layer first; if empty, OCR the rendered image
    text = page.get_text("text") or ""
    method = "text"
    lines = [l for l in text.splitlines() if l.strip()]
    if len("".join(lines)) < 40:
        lines = _ocr_lines(pix)
        method = "ocr" if lines else "none"
    doc.close()
    joined = "\n".join(lines)

    def grab(label):
        m = re.search(label + r"\s*[:：]\s*([^\n]+)", joined, re.I)
        return m.group(1).strip() if m else None

    parsed = {"survey_no": grab("Survey No"), "village": grab("Village"),
              "district": grab("District"), "taluk": grab("Taluk"),
              "area_sqm": None, "width_m": None, "depth_m": None, "dimensions": []}

    am = re.search(r"Hect\s*(\d+)\s*Ares\s*(\d+)\s*Sqm\s*(\d+)", joined, re.I)
    if am:
        h, a, s = map(int, am.groups())
        parsed["area_sqm"] = h * 10000 + a * 100 + s

    # plot edge dimensions: decimals like 12.2, 17.6 (plausible metres 1..500)
    dims = []
    for ln in lines:
        for x in re.findall(r"\b\d{1,3}\.\d{1,2}\b", ln):
            v = float(x)
            if 1.0 <= v <= 500.0:
                dims.append(round(v, 2))
    parsed["dimensions"] = dims
    if dims:
        parsed["width_m"] = min(dims)
        parsed["depth_m"] = max(dims)

    # which engine-input fields are present vs missing
    fields = {
        "survey_no": parsed["survey_no"], "village": parsed["village"],
        "area_sqm": parsed["area_sqm"], "width_m": parsed["width_m"], "depth_m": parsed["depth_m"],
    }
    detected = {k: v is not None for k, v in fields.items()}
    # these never come from an FMB — always flag for manual entry
    missing = [k for k, ok in detected.items() if not ok]
    missing += ["abutting_road_width", "local_body"]

    return {"preview_png_b64": png_b64, "method": method,
            "parsed": parsed, "detected": detected, "missing": missing,
            "has_text_layer": method == "text"}
