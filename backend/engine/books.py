"""Reference-books data layer: topic index, full-text search, page-image render.

Backs the 'Neufert Data' assistant. All answers are grounded in real rendered
book pages: we retrieve relevant page numbers (by selected topic and/or a
full-text search of the question) and hand the real rendered page images to
the vision model.
"""
import json, sqlite3, re, threading
from functools import lru_cache
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent.parent
BOOKS_DIR = ROOT / "data" / "books"
CACHE_DIR = BOOKS_DIR / "cache"
INDEX_PATH = BOOKS_DIR / "books_index.json"
DB_PATH = BOOKS_DIR / "books.db"

_INDEX = None
_DOCS = {}
_LOCK = threading.Lock()


def available() -> bool:
    return INDEX_PATH.exists() and DB_PATH.exists()


def load_index() -> dict:
    global _INDEX
    if _INDEX is None:
        _INDEX = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() \
            else {"books": {}, "chapters": []}
    return _INDEX


def book_meta(book_id: str) -> dict:
    return load_index().get("books", {}).get(book_id, {})


def topics_payload() -> dict:
    """Frontend payload: books + chapter-grouped topics for the radio list."""
    idx = load_index()
    out = {"books": [], "chapters": []}
    for bid, meta in idx.get("books", {}).items():
        out["books"].append({"id": bid, "title": meta.get("title", bid),
                             "label": meta.get("label", bid), "pages": meta.get("pages")})
    for ch in idx.get("chapters", []):
        out["chapters"].append({
            "book": ch["book"], "title": ch["title"],
            "page": ch["page"], "page_end": ch.get("page_end", ch["page"]),
            "children": ch.get("children", []),
        })
    return out


def _doc(book_id: str):
    with _LOCK:
        if book_id not in _DOCS:
            meta = book_meta(book_id)
            f = meta.get("file") or f"{book_id}.pdf"
            _DOCS[book_id] = fitz.open(str(BOOKS_DIR / f))
        return _DOCS[book_id]


def _fts_query(q: str) -> str:
    """Build a safe FTS5 OR-query from free text."""
    words = re.findall(r"[A-Za-z0-9]+", q.lower())
    words = [w for w in words if len(w) > 2][:12]
    return " OR ".join(words) if words else ""


def search(query: str, book: str = None, limit: int = 6) -> list:
    """Return [{book, page, snippet}] most relevant to query (FTS, or LIKE fallback)."""
    if not query.strip() or not DB_PATH.exists():
        return []
    con = sqlite3.connect(str(DB_PATH))
    rows = []
    try:
        fq = _fts_query(query)
        params = [fq]
        sql = ("SELECT book, page, snippet(pages, 2, '', '', ' … ', 12) "
               "FROM pages WHERE pages MATCH ?")
        if book:
            sql += " AND book = ?"; params.append(book)
        sql += " ORDER BY rank LIMIT ?"; params.append(limit)
        rows = con.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        # non-FTS fallback
        terms = re.findall(r"[A-Za-z0-9]+", query.lower())[:6]
        like = " OR ".join(["lower(text) LIKE ?"] * len(terms)) or "1=0"
        params = [f"%{t}%" for t in terms]
        sql = f"SELECT book, page, substr(text,1,160) FROM pages WHERE ({like})"
        if book:
            sql += " AND book = ?"; params.append(book)
        sql += " LIMIT ?"; params.append(limit)
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [{"book": b, "page": p, "snippet": (s or "").strip()} for (b, p, s) in rows]


def context_pages(question: str, book: str = None, topic_page: int = None,
                  topic_page_end: int = None, max_pages: int = 5) -> list:
    """Choose the page set to send to the vision model.

    Strategy: start with the selected topic's first page(s), then add the
    best full-text search hits for the question. De-duplicated, capped.
    """
    chosen = []
    seen = set()

    def add(bk, pg):
        key = (bk, pg)
        if key not in seen and 1 <= pg <= (book_meta(bk).get("pages") or 10 ** 6):
            seen.add(key); chosen.append({"book": bk, "page": pg})

    if book and topic_page:
        end = topic_page_end or topic_page
        # the topic's opening spread (cap 2 pages here; search adds the rest)
        for pg in range(topic_page, min(end, topic_page + 1) + 1):
            add(book, pg)

    for hit in search(question, book=book, limit=max_pages + 2):
        add(hit["book"], hit["page"])
        if len(chosen) >= max_pages:
            break

    return chosen[:max_pages]


@lru_cache(maxsize=512)
def render_page(book_id: str, page: int, dpi: int = 130) -> bytes:
    """Render a 1-based page to JPEG bytes (cached on disk + in memory)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_f = CACHE_DIR / f"{book_id}_{page}_{dpi}.jpg"
    if cache_f.exists():
        return cache_f.read_bytes()
    doc = _doc(book_id)
    page = max(1, min(page, doc.page_count))
    pix = doc[page - 1].get_pixmap(dpi=dpi)
    try:
        data = pix.tobytes("jpeg", jpg_quality=72)
        ext_ok = True
    except Exception:
        data = pix.tobytes("png")
        ext_ok = False
    if ext_ok:
        cache_f.write_bytes(data)
    return data


def snippet_for(book_id: str, page: int, limit: int = 600) -> str:
    """Plain text of a page (for an optional text hint alongside the image)."""
    con = sqlite3.connect(str(DB_PATH))
    try:
        row = con.execute("SELECT text FROM pages WHERE book=? AND page=?",
                          (book_id, page)).fetchone()
    finally:
        con.close()
    return ((row[0] if row else "") or "")[:limit]
