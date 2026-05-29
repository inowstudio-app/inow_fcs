"""Extract text from all DCR PDFs into data/text/ and print a structural summary."""
import fitz, os, glob, json

SRC = r"D:\CLAUDE\DCR"
OUT = r"D:\CLAUDE\DCR\data\text"
os.makedirs(OUT, exist_ok=True)

summary = []
for pdf in sorted(glob.glob(os.path.join(SRC, "*.pdf"))):
    name = os.path.splitext(os.path.basename(pdf))[0]
    doc = fitz.open(pdf)
    n = doc.page_count
    toc = doc.get_toc()  # [[level, title, page], ...]
    # dump full text page-delimited
    parts = []
    chars = 0
    for i, page in enumerate(doc):
        t = page.get_text("text")
        chars += len(t)
        parts.append(f"\n\n===== PAGE {i+1} =====\n{t}")
    with open(os.path.join(OUT, name + ".txt"), "w", encoding="utf-8") as f:
        f.write("".join(parts))
    summary.append({
        "file": os.path.basename(pdf),
        "pages": n,
        "text_chars": chars,
        "has_text_layer": chars > 200,  # else likely scanned/needs OCR
        "toc_entries": len(toc),
    })
    doc.close()

print(json.dumps(summary, indent=2))
# print TOC of the two core docs if present
for core in ("TNCDBR-2019", "TNCDRBR-2019"):
    p = os.path.join(SRC, core + ".pdf")
    if os.path.exists(p):
        d = fitz.open(p)
        toc = d.get_toc()
        print(f"\n##### TOC: {core} ({len(toc)} entries) #####")
        for lvl, title, pg in toc[:80]:
            print(f"{'  '*(lvl-1)}p{pg}: {title}")
        d.close()
