import argparse
import json
import re
from collections import Counter

import pdfplumber
from PyPDF2 import PdfReader


# Tuned for technical book material:
# medium chunks preserve enough local concept flow while remaining specific for retrieval.
DEFAULT_TARGET_WORDS = 450
DEFAULT_MAX_WORDS = 700
DEFAULT_OVERLAP_WORDS = 90
DEFAULT_MIN_CHUNK_WORDS = 220
DEFAULT_MIN_SECTION_WORDS = 80


def get_bookmark_chunks(pdf_path):
    reader = PdfReader(pdf_path)
    outlines = reader.outline  # PyPDF2 3.x+
    bookmarks = []

    def recurse(outline):
        if isinstance(outline, list):
            for o in outline:
                recurse(o)
            return
        try:
            title = (outline.title or "").strip()
            page_num = reader.get_destination_page_number(outline)
            if title:
                bookmarks.append((title, page_num))
        except Exception:
            pass

    try:
        recurse(outlines)
    except Exception:
        return []

    if not bookmarks:
        return []

    # Keep only the first bookmark per start page to avoid repeated nested entries.
    deduped = {}
    for title, page in sorted(bookmarks, key=lambda x: x[1]):
        deduped.setdefault(page, title)
    sorted_pages = sorted(deduped.items(), key=lambda x: x[0])

    chunks = []
    for i, (start_page, title) in enumerate(sorted_pages):
        end_page = sorted_pages[i + 1][0] if i + 1 < len(sorted_pages) else None
        chunks.append((title, start_page, end_page))
    return chunks


def _normalize_line(line):
    line = line.strip()
    line = re.sub(r"\s+", " ", line)
    return line


def _remove_repeated_page_noise(page_lines_by_page):
    # Identify short lines that repeat on many pages (headers/footers/page counters).
    normalized_lines = []
    for lines in page_lines_by_page:
        normalized_lines.extend({_normalize_line(l) for l in lines if _normalize_line(l)})

    total_pages = len(page_lines_by_page)
    line_counter = Counter(normalized_lines)
    repeated_noise = set()
    for line, count in line_counter.items():
        if len(line) <= 90 and count >= max(4, total_pages // 4):
            if re.search(r"\bpage\b|\d+\s*/\s*\d+|copyright|all rights reserved", line, re.I):
                repeated_noise.add(line)
            elif len(re.findall(r"[A-Za-z]", line)) < 5:
                repeated_noise.add(line)

    cleaned_pages = []
    for lines in page_lines_by_page:
        kept = []
        for line in lines:
            nl = _normalize_line(line)
            if not nl:
                continue
            if nl in repeated_noise:
                continue
            kept.append(line)
        cleaned_pages.append(kept)
    return cleaned_pages


def _clean_page_text(lines):
    text = "\n".join(lines)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Dehyphenate line-break splits: "devel-\nopment" -> "development"
    text = re.sub(r"([A-Za-z])-\n([A-Za-z])", r"\1\2", text)
    # Keep paragraph boundaries but unwrap regular line wraps.
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _word_count(text):
    return len(re.findall(r"\S+", text))


def _extractive_summary(text, max_chars=420):
    if not text:
        return ""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sentences:
        return text[:max_chars]
    summary = " ".join(sentences[:2]).strip()
    if len(summary) > max_chars:
        summary = summary[: max_chars - 3].rstrip() + "..."
    return summary


def _chunk_text(text, target_words, max_words, overlap_words, min_chunk_words):
    words = re.findall(r"\S+", text)
    if not words:
        return []

    chunks = []
    start = 0
    n = len(words)

    while start < n:
        hard_end = min(start + max_words, n)
        end = hard_end

        # Prefer ending near target_words at sentence-ish boundaries.
        if hard_end < n:
            scan_low = min(start + min_chunk_words, hard_end)
            scan_high = min(start + target_words + 90, hard_end)
            for idx in range(scan_high, scan_low - 1, -1):
                token = words[idx - 1]
                if re.search(r"[.!?][\"')\]]?$", token):
                    end = idx
                    break

        if end <= start:
            end = hard_end

        chunk_text = " ".join(words[start:end]).strip()
        if chunk_text:
            chunks.append(chunk_text)

        if end >= n:
            break
        start = max(end - overlap_words, start + 1)

    # Merge tiny tail.
    if len(chunks) > 1 and _word_count(chunks[-1]) < max(60, min_chunk_words // 3):
        chunks[-2] = (chunks[-2] + " " + chunks[-1]).strip()
        chunks.pop()

    return chunks


def _read_pdf_pages(pdf_path):
    page_lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            lines = [l for l in page_text.splitlines() if l.strip()]
            page_lines.append(lines)
    page_lines = _remove_repeated_page_noise(page_lines)
    return [_clean_page_text(lines) for lines in page_lines]


def _extract_sections(pdf_path, bookmarks, min_section_words=DEFAULT_MIN_SECTION_WORDS):
    pages = _read_pdf_pages(pdf_path)
    total_pages = len(pages)
    sections = []

    if bookmarks:
        for title, start_page, end_page in bookmarks:
            if start_page < 0 or start_page >= total_pages:
                continue
            end = end_page if end_page is not None else total_pages
            if end <= start_page:
                continue
            section_text = "\n\n".join(p for p in pages[start_page:end] if p).strip()
            if _word_count(section_text) >= min_section_words:
                sections.append((title, start_page + 1, end, section_text))
        return sections

    # Fallback: use document as a single source section.
    whole = "\n\n".join(p for p in pages if p).strip()
    if _word_count(whole) >= min_section_words:
        sections.append(("Document", 1, total_pages, whole))
    return sections


def main():
    parser = argparse.ArgumentParser(description="Extract PDF into RAG-friendly JSON chunks.")
    parser.add_argument("input_pdf", help="Path to input PDF.")
    parser.add_argument("output_json", help="Path to output JSON.")
    parser.add_argument("--target-words", type=int, default=DEFAULT_TARGET_WORDS)
    parser.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS)
    parser.add_argument("--overlap-words", type=int, default=DEFAULT_OVERLAP_WORDS)
    parser.add_argument("--min-chunk-words", type=int, default=DEFAULT_MIN_CHUNK_WORDS)
    args = parser.parse_args()

    if args.target_words <= 0 or args.max_words < args.target_words:
        raise ValueError("max-words must be >= target-words and target-words > 0")
    if args.overlap_words < 0 or args.overlap_words >= args.max_words:
        raise ValueError("overlap-words must be >=0 and less than max-words")

    print("Checking for bookmarks (chapters/sections) ...")
    bookmark_chunks = get_bookmark_chunks(args.input_pdf)

    if bookmark_chunks:
        print(f"Found {len(bookmark_chunks)} bookmarks. Building section-aware chunks ...")
    else:
        print("No bookmarks found. Falling back to document-level chunking ...")

    sections = _extract_sections(args.input_pdf, bookmark_chunks)
    items = []
    for title, start_page, end_page, section_text in sections:
        chunks = _chunk_text(
            section_text,
            target_words=args.target_words,
            max_words=args.max_words,
            overlap_words=args.overlap_words,
            min_chunk_words=args.min_chunk_words,
        )

        chunk_total = len(chunks)
        for i, chunk in enumerate(chunks, start=1):
            items.append(
                {
                    "input": f"{title} | chunk {i}/{chunk_total}",
                    "output": chunk,
                    "summary": _extractive_summary(chunk),
                    "source_title": title,
                    "start_page": start_page,
                    "end_page": end_page,
                    "chunk_index": i,
                    "chunk_total": chunk_total,
                    "word_count": _word_count(chunk),
                }
            )

    with open(args.output_json, "w", encoding="utf-8") as out:
        json.dump(items, out, ensure_ascii=False, indent=2)

    print(f"Done! Wrote {len(items)} chunks to {args.output_json}")


if __name__ == "__main__":
    main()
