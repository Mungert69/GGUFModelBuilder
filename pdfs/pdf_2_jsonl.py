import pdfplumber
from PyPDF2 import PdfReader
import re
import sys
import json

def get_bookmark_chunks(pdf_path):
    reader = PdfReader(pdf_path)
    outlines = reader.outline  # PyPDF2 3.x+
    bookmarks = []
    def recurse(outline):
        if isinstance(outline, list):
            for o in outline:
                recurse(o)
        else:
            try:
                title = outline.title
                page_num = reader.get_destination_page_number(outline)
                bookmarks.append((title, page_num))
            except Exception:
                pass
    try:
        recurse(outlines)
    except Exception:
        return []
    if not bookmarks:
        return []
    # Sort by page number
    bookmarks.sort(key=lambda x: x[1])
    # Build chapter page ranges
    chunks = []
    for i, (title, start_page) in enumerate(bookmarks):
        end_page = bookmarks[i+1][1] if i+1 < len(bookmarks) else None
        chunks.append((title, start_page, end_page))
    return chunks

def extract_bookmark_chunks(pdf_path, bookmarks, min_length=30):
    with pdfplumber.open(pdf_path) as pdf:
        blocks = []
        for title, start_page, end_page in bookmarks:
            pages = []
            end = end_page if end_page is not None else len(pdf.pages)
            for p in range(start_page, end):
                text = pdf.pages[p].extract_text()
                if text:
                    pages.append(text)
            block = "\n".join(pages).strip()
            if len(block) >= min_length:
                blocks.append((title, block))
        return blocks

def extract_paragraphs(pdf_path, min_length=30):
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    paragraphs = re.split(r'\n\s*\n', text)
    # Remove short/empty or garbage lines
    paragraphs = [p.strip() for p in paragraphs if len(p.strip()) > min_length]
    return paragraphs

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} input.pdf output.json")
        return

    input_pdf = sys.argv[1]
    output_json = sys.argv[2]

    print(f"Checking for bookmarks (chapters/sections) ...")
    bookmark_chunks = get_bookmark_chunks(input_pdf)

    items = []
    if bookmark_chunks:
        print(f"Found {len(bookmark_chunks)} bookmarks. Splitting by chapters/sections ...")
        blocks = extract_bookmark_chunks(input_pdf, bookmark_chunks)
        for title, block in blocks:
            items.append({
                "input": title,
                "output": block
            })
    else:
        print("No bookmarks found. Splitting by logical paragraphs ...")
        paragraphs = extract_paragraphs(input_pdf)
        for para in paragraphs:
            items.append({
                "input": "Paragraph",
                "output": para
            })

    with open(output_json, "w", encoding="utf-8") as out:
        json.dump(items, out, ensure_ascii=False, indent=2)
    print("Done!")

if __name__ == "__main__":
    main()
