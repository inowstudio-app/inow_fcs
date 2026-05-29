"""
DCR doubt-assistant. Answers design-stage questions against the TN DCR knowledge base,
optionally reading an uploaded hand-sketch (vision). Powered by the Anthropic Claude API.

Dormant until ANTHROPIC_API_KEY is set in the environment — status() reports configured=False
and ask() returns a friendly "not configured" message, so the app runs fine without a key.
"""
from __future__ import annotations
import base64, os

KB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "rules", "assistant_kb.md")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

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
- When a simple diagram would clarify the rule, include ONE minimal inline SVG inside a ```svg code fence \
(viewBox, plain shapes + text, no scripts). Keep it small and illustrative.
- Be concise and practical. Do not invent rules or numbers.

=== DCR KNOWLEDGE BASE ===
"""


def _kb() -> str:
    try:
        with open(KB_PATH, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "(knowledge base unavailable)"


def status() -> dict:
    return {"configured": bool(os.environ.get("ANTHROPIC_API_KEY")), "model": MODEL}


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

    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=MODEL, max_tokens=1200,
            system=SYSTEM + _kb(),
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        if not text.strip():
            text = "(The model returned no text — try rephrasing your question.)"
        usage = getattr(msg, "usage", None)
        return {"configured": True, "answer": text, "model": MODEL,
                "usage": {"input": getattr(usage, "input_tokens", None),
                          "output": getattr(usage, "output_tokens", None)} if usage else None}
    except Exception as e:  # surface the real cause to the UI
        return {"configured": True, "model": MODEL,
                "answer": f"⚠ Assistant error: {type(e).__name__}: {e}"}
