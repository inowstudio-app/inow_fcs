"""Ingest the architect reference books (Neufert, Architect's Data).

Produces, under data/books/:
  - copies of the source PDFs (so they ship with the deployment)
  - books_index.json  : topic list (chapter-grouped) -> page ranges, per book
  - books.db          : sqlite (FTS5 if available) of per-page text for retrieval

Page-image rendering is done on demand by engine/books.py (cached), not here.

Run:  python backend/ingest/build_books.py
"""
import os, sys, json, shutil, sqlite3, re
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent.parent
BOOKS_DIR = ROOT / "data" / "books"
BOOKS_DIR.mkdir(parents=True, exist_ok=True)

# (book_id, title, source path, short label)
SOURCES = [
    ("neufert", "Neufert — Architects' Data",
     Path(os.environ.get("NEUFERT_SRC", r"C:\Users\inowo.NARENINOW\Downloads\Neufert-S.pdf")),
     "Neufert"),
    ("architects_data", "Architect's Data",
     Path(os.environ.get("ARCHDATA_SRC", r"C:\Users\inowo.NARENINOW\Downloads\03. Architect_s Data.pdf")),
     "Architect's Data"),
]

HEADING_MIN = 3      # min chars for a derived heading
HEADING_MAX = 70     # max chars (titles are short)


def copy_pdf(src: Path, book_id: str) -> Path:
    dst = BOOKS_DIR / f"{book_id}.pdf"
    if not dst.exists() or dst.stat().st_size != src.stat().st_size:
        print(f"  copying {src.name} -> {dst.name} ({src.stat().st_size/1e6:.1f} MB)")
        shutil.copyfile(src, dst)
    else:
        print(f"  {dst.name} already present")
    return dst


def toc_topics(doc) -> list:
    """Build topics from an embedded TOC. Returns flat list with page ranges."""
    toc = doc.get_toc(simple=True)  # [level, title, page]
    entries = [{"level": lv, "title": t.strip(), "page": pg}
               for (lv, t, pg) in toc if pg and pg > 0 and t.strip()]
    # compute end page = (next entry start - 1), else last page
    n = doc.page_count
    topics = []
    for i, e in enumerate(entries):
        end = n
        for j in range(i + 1, len(entries)):
            if entries[j]["page"] > e["page"]:
                end = entries[j]["page"] - 1
                break
        if end < e["page"]:
            end = e["page"]
        topics.append({"title": e["title"], "level": e["level"],
                       "page": e["page"], "page_end": end})
    return topics


def derive_topics(doc) -> list:
    """No TOC: use the largest-font text line on each page as a topic candidate."""
    topics = []
    prev = None
    for pno in range(doc.page_count):
        page = doc[pno]
        try:
            d = page.get_text("dict")
        except Exception:
            continue
        best_size, best_text = 0, ""
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = (span.get("text") or "").strip()
                    sz = span.get("size", 0)
                    if len(txt) < HEADING_MIN or len(txt) > HEADING_MAX:
                        continue
                    # prefer alphabetic, title-ish lines
                    if not re.search(r"[A-Za-z]", txt):
                        continue
                    if sz > best_size:
                        best_size, best_text = sz, txt
        title = re.sub(r"\s+", " ", best_text).strip(" .:-—·")
        if not title:
            continue
        # skip near-duplicate consecutive headings
        if prev and title.lower() == prev.lower():
            topics[-1]["page_end"] = pno + 1
            continue
        topics.append({"title": title, "level": 1, "page": pno + 1, "page_end": pno + 1})
        prev = title
    return topics


def group_chapters(topics: list) -> list:
    """Group flat topics under their nearest preceding level-1 heading."""
    chapters = []
    cur = None
    for t in topics:
        if t["level"] <= 1 or cur is None:
            cur = {"title": t["title"], "page": t["page"], "page_end": t["page_end"],
                   "children": []}
            chapters.append(cur)
            if t["level"] <= 1:
                continue
        cur["children"].append({"title": t["title"], "page": t["page"],
                                "page_end": t["page_end"]})
        cur["page_end"] = max(cur["page_end"], t["page_end"])
    return chapters


def build_search_db(books_pages: dict):
    db_path = BOOKS_DIR / "books.db"
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(str(db_path))
    fts = True
    try:
        con.execute("CREATE VIRTUAL TABLE pages USING fts5(book, page UNINDEXED, text)")
    except sqlite3.OperationalError:
        fts = False
        con.execute("CREATE TABLE pages (book TEXT, page INT, text TEXT)")
    rows = []
    for book_id, pages in books_pages.items():
        for pno, text in pages:
            rows.append((book_id, pno, text))
    con.executemany("INSERT INTO pages (book, page, text) VALUES (?,?,?)", rows)
    con.commit()
    con.close()
    print(f"  search DB: {len(rows)} pages  (FTS5={fts})")
    return fts


def main():
    index = {"books": {}, "chapters": []}
    books_pages = {}
    for book_id, title, src, label in SOURCES:
        print(f"[{book_id}] {title}")
        if not src.exists():
            print(f"  !! source missing: {src}")
            continue
        copy_pdf(src, book_id)
        doc = fitz.open(str(BOOKS_DIR / f"{book_id}.pdf"))
        n = doc.page_count
        toc = doc.get_toc(simple=True)
        flat = toc_topics(doc) if toc else derive_topics(doc)
        chapters = group_chapters(flat)
        index["books"][book_id] = {
            "id": book_id, "title": title, "label": label,
            "file": f"{book_id}.pdf", "pages": n,
            "topic_source": "toc" if toc else "derived",
            "chapter_count": len(chapters), "topic_count": len(flat),
        }
        for ch in chapters:
            index["chapters"].append({"book": book_id, **ch})
        # per-page text
        pages = []
        for pno in range(n):
            txt = doc[pno].get_text().strip()
            pages.append((pno + 1, txt))
        books_pages[book_id] = pages
        print(f"  pages={n}  chapters={len(chapters)}  topics={len(flat)}  "
              f"source={'TOC' if toc else 'derived'}")
        doc.close()

    build_search_db(books_pages)
    (BOOKS_DIR / "books_index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {BOOKS_DIR / 'books_index.json'}  "
          f"({len(index['chapters'])} chapters total)")


if __name__ == "__main__":
    main()
