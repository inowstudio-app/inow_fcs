"""
DCR doubt-assistant. Answers design-stage questions against the TN DCR knowledge base,
optionally reading an uploaded hand-sketch (vision). Powered by the Anthropic Claude API.

Dormant until ANTHROPIC_API_KEY is set in the environment — status() reports configured=False
and ask() returns a friendly "not configured" message, so the app runs fine without a key.
"""
from __future__ import annotations
import base64, os

from engine.svgutil import extract_and_sanitize

KB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "rules", "assistant_kb.md")
MODEL_ENV = os.environ.get("ANTHROPIC_MODEL")  # optional explicit override
_RESOLVED_MODEL = None


def _resolve_model(client) -> str:
    """Use ANTHROPIC_MODEL if set; else auto-pick from the models the key can access
    (prefer Sonnet, then Opus, then Haiku, then newest). Cached after first lookup."""
    global _RESOLVED_MODEL
    if MODEL_ENV:
        return MODEL_ENV
    if _RESOLVED_MODEL:
        return _RESOLVED_MODEL
    try:
        ids = [m.id for m in client.models.list(limit=100).data]  # newest first
        pick = (next((i for i in ids if "sonnet" in i.lower()), None)
                or next((i for i in ids if "opus" in i.lower()), None)
                or next((i for i in ids if "haiku" in i.lower()), None)
                or (ids[0] if ids else None))
        _RESOLVED_MODEL = pick or "claude-3-5-haiku-latest"
    except Exception:
        _RESOLVED_MODEL = "claude-3-5-haiku-latest"
    return _RESOLVED_MODEL

SYSTEM = """You are a Tamil Nadu DCR expert assistant for architects, grounded in the \
Tamil Nadu Combined Development & Building Rules, 2019 (with amendments). Answer design-stage \
questions (e.g. whether a staircase, toilet, balcony or projection may extend into a setback).

Rules of engagement:
- Use ONLY the DCR knowledge base provided below. If the answer isn't covered, say so plainly \
and suggest what official clause or authority to check.
- Always start with a one-word VERDICT on its own line: "VERDICT: Allowed" / "VERDICT: Not allowed" / "VERDICT: Conditional".
- Then give a short, specific explanation and cite the exact rule/clause (e.g. "Rule 28(a)(iii)").
- State the numeric conditions/limits that apply (e.g. distances, heights).
- If an image (sketch) is provided, interpret what it shows and answer about that specific situation.
- Be concise and practical. Do not invent rules or numbers.

DIAGRAMS — when a simple diagram clarifies the rule, include ONE inline SVG inside a ```svg code \
fence. It MUST be clean and legible — follow every rule:
- Use viewBox="0 0 800 600". Put NOTHING outside the viewBox.
- Keep generous padding (>=30px from all edges). Never let text touch or overlap a line, shape, \
or other text. If two labels would collide, move one onto its own clear leader line.
- Font: >=14px for labels, >=16px for the title; never below 12px. One title at the top.
- Draw real geometry to scale where dimensions matter (e.g. a setback section): a plot/wall \
rectangle, the element, and dimension lines with arrowheads and a numeric label per dimension.
- Restrained palette: dark slate (#334155) strokes, ONE accent colour (#1668b3 or #1f9d5c) for the \
element in question, light grey (#e2e8f0) for guides. Stroke width 1-2px.
- Label every element once, placed beside it (not on top). Add a small legend only if needed.
- No scripts, no animation, no foreignObject. Keep it a clear technical sketch, not decorative.

=== DCR KNOWLEDGE BASE ===
"""


def _kb() -> str:
    try:
        with open(KB_PATH, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "(knowledge base unavailable)"


def status() -> dict:
    return {"configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "model": MODEL_ENV or _RESOLVED_MODEL or "auto-detect"}


def ask(question: str, image_bytes: bytes | None = None, image_media_type: str | None = None) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"configured": False,
                "answer": "The DCR Assistant isn't switched on yet. Add an ANTHROPIC_API_KEY "
                          "in the server environment (Render → Environment) to enable it."}
    try:
        import anthropic
    except ImportError:
        return {"configured": False, "answer": "The 'anthropic' package is not installed on the server."}

    content = []
    if image_bytes:
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": image_media_type or "image/png",
            "data": base64.b64encode(image_bytes).decode("ascii")}})
    content.append({"type": "text", "text": question or "Please review the attached sketch against the TN DCR."})

    model = None
    try:
        client = anthropic.Anthropic()
        model = _resolve_model(client)
        msg = client.messages.create(
            model=model, max_tokens=1200,
            system=SYSTEM + _kb(),
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        if not text.strip():
            text = "(The model returned no text — try rephrasing your question.)"
        # pull out + clean any diagram so it always renders legibly
        clean_text, svg = extract_and_sanitize(text)
        usage = getattr(msg, "usage", None)
        return {"configured": True, "answer": clean_text or text, "svg": svg, "model": model,
                "usage": {"input": getattr(usage, "input_tokens", None),
                          "output": getattr(usage, "output_tokens", None)} if usage else None}
    except Exception as e:  # surface the real cause to the UI
        return {"configured": True, "model": model,
                "answer": f"⚠ Assistant error: {type(e).__name__}: {e}"}
