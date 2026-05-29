"""Make model-generated SVGs clean and legible.

The vision model sometimes emits SVGs with no background (unreadable), a missing
xmlns, tiny/!default fonts, or stray <script>. This normalizer enforces a baseline
so every diagram the assistants show is readable, without trying to re-layout the
drawing itself (that's the model's job, guided by the prompt rules).
"""
import re

_VIEWBOX_RE = re.compile(r'viewBox\s*=\s*"([\d.\-\s]+)"', re.I)
_SVG_OPEN_RE = re.compile(r'<svg\b[^>]*>', re.I)
_SCRIPT_RE = re.compile(r'<script\b[\s\S]*?</script>', re.I)
_ON_ATTR_RE = re.compile(r'\son\w+\s*=\s*"[^"]*"', re.I)
_FOREIGN_RE = re.compile(r'<foreignObject\b[\s\S]*?</foreignObject>', re.I)


def sanitize_svg(svg: str) -> str | None:
    """Return a cleaned single <svg>…</svg>, or None if no svg present."""
    if not svg:
        return None
    m = re.search(r'<svg[\s\S]*?</svg>', svg, re.I)
    if not m:
        return None
    s = m.group(0)

    # security: drop scripts, inline event handlers, foreignObject
    s = _SCRIPT_RE.sub("", s)
    s = _ON_ATTR_RE.sub("", s)
    s = _FOREIGN_RE.sub("", s)

    open_m = _SVG_OPEN_RE.search(s)
    open_tag = open_m.group(0)
    new_open = open_tag

    # ensure xmlns
    if "xmlns" not in new_open:
        new_open = new_open[:-1] + ' xmlns="http://www.w3.org/2000/svg">'

    # ensure a font-family default on the root (so text isn't a serif default)
    if "font-family" not in new_open:
        new_open = new_open[:-1] + ' font-family="Segoe UI, Arial, sans-serif">'

    # determine viewBox (synthesize from width/height if absent)
    vb = _VIEWBOX_RE.search(new_open)
    if not vb:
        w = re.search(r'\bwidth\s*=\s*"?(\d+)', new_open)
        h = re.search(r'\bheight\s*=\s*"?(\d+)', new_open)
        W = int(w.group(1)) if w else 800
        H = int(h.group(1)) if h else 600
        new_open = new_open[:-1] + f' viewBox="0 0 {W} {H}">'
        vb_vals = [0, 0, W, H]
    else:
        try:
            vb_vals = [float(x) for x in vb.group(1).split()]
        except Exception:
            vb_vals = [0, 0, 800, 600]

    s = s.replace(open_tag, new_open, 1)

    # ensure a white background rectangle right after the opening tag
    if "data-bg" not in s:
        x, y, w, h = (vb_vals + [0, 0, 800, 600])[:4]
        bg = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#ffffff" data-bg="1"/>'
        s = re.sub(_SVG_OPEN_RE, lambda mm: mm.group(0) + bg, s, count=1)

    return s


def extract_and_sanitize(text: str):
    """Pull an SVG out of model text (raw <svg> or ```svg fence), sanitize it.

    Returns (text_without_svg, svg_or_none).
    """
    if not text:
        return text, None
    svg = None
    # fenced ```svg ... ```
    fence = re.search(r'```svg\s*([\s\S]*?)```', text, re.I)
    if fence:
        svg = fence.group(1)
        text = (text[:fence.start()] + text[fence.end():]).strip()
    else:
        m = re.search(r'<svg[\s\S]*?</svg>', text, re.I)
        if m:
            svg = m.group(0)
            text = (text[:m.start()] + text[m.end():]).strip()
    return text, (sanitize_svg(svg) if svg else None)
