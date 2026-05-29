"""'Neufert Data' assistant routes — grounded Q&A over the reference books.

All answers are grounded in real rendered book pages handed to the vision
model, which is instructed to cite page numbers and to refuse (or ask a
clarifying question) rather than invent anything not in the books.
"""
import json, base64, re
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response

from engine import books
from engine import sunpath
from engine.svgutil import extract_and_sanitize
from engine.llm import get_client, pick_model

router = APIRouter(prefix="/api/books", tags=["books"])

# Deterministic diagram tools the model may call. The SERVER computes these
# exactly (real geometry) and returns the SVG — the model never draws them itself.
TOOLS = [
    {
        "name": "draw_sun_path",
        "description": (
            "Generate a PRECISE sun-path diagram (horizontal/polar projection) for a "
            "location, computed from real solar geometry. Use this whenever the user asks "
            "for a sun-path / sun chart / solar access diagram. Requires a latitude OR a "
            "recognised city name — if you don't have either yet, DON'T call this; ask the "
            "user first. Returns an SVG that is shown to the user automatically, plus a "
            "summary of sunrise/sunset/noon-altitude per key date for you to explain."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number",
                             "description": "Site latitude in degrees (north +, south -). e.g. Chennai 13.08"},
                "city": {"type": "string",
                         "description": "City name if latitude unknown (e.g. 'Coimbatore'). Used to look up latitude."},
                "place": {"type": "string", "description": "Label to show on the diagram (e.g. site/town name)."},
                "north_offset_deg": {"type": "number",
                                     "description": "Clockwise rotation so the chart's up matches the plot's North, if the user's sketch North is rotated. 0 = geographic north up."},
                "date": {"type": "string",
                         "description": "Optional extra date in YYYY-MM-DD to overlay (besides solstices/equinox)."},
            },
        },
    },
]

SYSTEM = """You are the "Neufert Data" assistant for a Tamil Nadu architecture practice.
You answer design questions STRICTLY from the architect reference books whose
actual scanned pages are supplied to you as images in each request (Neufert —
Architects' Data, and Architect's Data).

HARD RULES — never break these:
1. Ground every statement in the supplied book pages. Cite them inline like
   "(Neufert p.123)". If several pages are given, cite the specific one.
2. If the supplied pages do NOT contain the answer, say plainly:
   "The supplied book pages don't cover this — try selecting a more specific
   topic." Do NOT answer from outside knowledge. Never invent figures.
3. If a precise/scaled or location-dependent diagram is requested (e.g. a sun-path
   diagram, a daylight angle, a parking-bay layout) and you are missing inputs you
   need to draw it correctly (location/latitude, date/season, orientation, plot
   dimensions, scale), ASK for those inputs first in a short numbered list.
   Do not draw a guessed/approximate version.
4. Read the user's attached sketch (if any) carefully and refer to what it shows.

TOOLS:
- For a SUN-PATH diagram, you have a tool `draw_sun_path` that computes the chart
  from exact solar geometry. Never hand-draw a sun-path as SVG yourself. First make
  sure you have the latitude or a city name (and, if the user's sketch North is
  rotated, the north offset). If missing, ASK; otherwise call the tool. After the
  tool returns, explain the result using its summary figures and, where helpful,
  relate it to the book's daylighting/orientation guidance with a page citation.

DIAGRAMS — when you DO draw, the drawing must be clean and legible:
- Emit ONE <svg> ... </svg> block, viewBox="0 0 800 600", with a white/very-light
  background <rect>.
- Never overlap text with lines or other text. Keep >=14px font, left/right padding
  >=24px. Put dimension labels on their own clear leader lines.
- Use a light grid only if it aids reading. Label every element. Include a small
  legend and a title. Keep stroke widths 1-2px. Use a restrained palette
  (dark slate strokes, one accent colour). Prefer fewer, well-placed labels.
- If the diagram encodes book data, annotate values with their citation.

Be concise and practical. Use the practice's units when the user does."""


@router.get("/topics")
def topics():
    if not books.available():
        raise HTTPException(503, "Books not ingested. Run backend/ingest/build_books.py.")
    return books.topics_payload()


@router.get("/page/{book_id}/{page}.jpg")
def page_image(book_id: str, page: int, dpi: int = 130):
    if not books.available():
        raise HTTPException(404, "Books not available")
    try:
        data = books.render_page(book_id, page, dpi=dpi)
    except Exception as e:
        raise HTTPException(404, f"page render failed: {e}")
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.post("/ask")
async def ask(
    question: str = Form(...),
    book: Optional[str] = Form(None),
    topic_title: Optional[str] = Form(None),
    topic_page: Optional[int] = Form(None),
    topic_page_end: Optional[int] = Form(None),
    history: str = Form("[]"),
    sketch: Optional[UploadFile] = File(None),
):
    if not books.available():
        raise HTTPException(503, "Books not ingested.")
    client = get_client()
    if client is None:
        raise HTTPException(503, "Assistant not configured (no ANTHROPIC_API_KEY).")
    model = pick_model(client)

    book = book or None
    # whole-book / all-books mode (no topic anchor) -> widen the search net for recall
    max_ctx = 5 if topic_page else 8
    pages = books.context_pages(question, book=book, topic_page=topic_page,
                                topic_page_end=topic_page_end, max_pages=max_ctx)
    if not pages and topic_page and book:
        pages = [{"book": book, "page": topic_page}]

    # ---- build the user message: book pages, then sketch, then question ----
    content = []
    topic_note = f"Selected topic: {topic_title}" if topic_title else "No topic selected."
    content.append({"type": "text",
                    "text": f"{topic_note}\nReference pages supplied below "
                            f"(cite these). Answer only from them."})
    sources = []
    for pg in pages:
        meta = books.book_meta(pg["book"])
        label = f"{meta.get('label', pg['book'])} p.{pg['page']}"
        content.append({"type": "text", "text": f"[{label}]"})
        try:
            img = books.render_page(pg["book"], pg["page"], dpi=130)
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": base64.standard_b64encode(img).decode()}})
            sources.append({"book": pg["book"], "page": pg["page"], "label": label,
                            "url": f"/api/books/page/{pg['book']}/{pg['page']}.jpg"})
        except Exception:
            continue

    if sketch is not None:
        raw = await sketch.read()
        if raw:
            content.append({"type": "text", "text": "User's attached sketch/drawing:"})
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": sketch.content_type or "image/png",
                "data": base64.standard_b64encode(raw).decode()}})

    content.append({"type": "text", "text": f"Question: {question}"})

    # prior turns as plain text (don't resend page images — saves tokens)
    msgs = []
    try:
        for h in json.loads(history or "[]"):
            role = h.get("role"); txt = h.get("text") or ""
            if role in ("user", "assistant") and txt:
                msgs.append({"role": role, "content": txt})
    except Exception:
        pass
    msgs.append({"role": "user", "content": content})

    svg = None  # a deterministic tool may set this

    def run_tool(name, tool_input):
        """Execute a server-side diagram tool. Returns (result_text, svg_or_none)."""
        if name == "draw_sun_path":
            try:
                r = sunpath.compute(
                    latitude=tool_input.get("latitude"),
                    city=tool_input.get("city", "") or "",
                    place=tool_input.get("place", "") or "",
                    north_offset_deg=tool_input.get("north_offset_deg", 0) or 0,
                    date=tool_input.get("date"),
                )
                summary = json.dumps({"latitude": r["latitude"], "place": r["place"],
                                      "summary": r["summary"]})
                return ("Sun-path diagram generated and shown to the user. "
                        "Key figures (solar time): " + summary), r["svg"]
            except Exception as e:
                return (f"Could not generate the sun-path: {e}. "
                        "Ask the user for the site latitude or a city name."), None
        return (f"Unknown tool {name}.", None)

    # tool-use loop (cap iterations defensively)
    try:
        for _ in range(4):
            resp = client.messages.create(model=model, max_tokens=2200,
                                           system=SYSTEM, tools=TOOLS, messages=msgs)
            if resp.stop_reason != "tool_use":
                break
            # echo the assistant's tool-call turn, then provide results
            msgs.append({"role": "assistant", "content": resp.content})
            results = []
            for blk in resp.content:
                if getattr(blk, "type", None) == "tool_use":
                    out_text, out_svg = run_tool(blk.name, blk.input or {})
                    if out_svg:
                        svg = out_svg
                    results.append({"type": "tool_result", "tool_use_id": blk.id,
                                    "content": out_text})
            msgs.append({"role": "user", "content": results})
    except Exception as e:
        raise HTTPException(500, f"Assistant error: {e}")

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    # if the model also emitted an inline diagram (non-tool), clean + use it when no tool svg
    clean_text, inline_svg = extract_and_sanitize(text)
    if inline_svg:
        text = clean_text
        if svg is None:
            svg = inline_svg
    return {"answer": text, "svg": svg, "sources": sources, "model": model}
