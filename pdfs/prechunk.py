# prechunk.py
import re

def smart_prechunk(text, tokenizer, chunk_token_limit):
    heading_regex = re.compile(
        r'(?m)^(?:[A-Z][A-Z0-9 .:-]{3,}|Chapter\s+\d+|Section\s+\d+|Appendix\s+[A-Z]|\d+\.\d+.*?)\s*$'
    )
    parts = []
    last = 0
    for m in heading_regex.finditer(text):
        start = m.start()
        if start > last:
            parts.append(text[last:start].strip())
        last = start
    if last < len(text):
        parts.append(text[last:].strip())
    if len(parts) <= 1:
        parts = [p.strip() for p in text.split('\n\n') if p.strip()]
    final_chunks = []
    for part in parts:
        if len(tokenizer.encode(part)) > chunk_token_limit:
            sentences = re.split(r'(?<=[.!?])\s+', part)
            buf = ""
            for sent in sentences:
                if len(tokenizer.encode(buf + " " + sent)) > chunk_token_limit:
                    final_chunks.append(buf.strip())
                    buf = sent
                else:
                    buf += " " + sent
            if buf.strip():
                final_chunks.append(buf.strip())
        else:
            final_chunks.append(part)
    return [c for c in final_chunks if c.strip()]

def merge_chunks(chunks, tokenizer, min_chunk_tokens):
    merged_chunks = []
    buf = ""
    buf_tokens = 0
    for chunk in chunks:
        chunk_tokens = len(tokenizer.encode(chunk))
        if buf_tokens + chunk_tokens < min_chunk_tokens:
            buf = (buf + "\n\n" + chunk).strip()
            buf_tokens += chunk_tokens
        else:
            if buf:
                merged_chunks.append(buf)
            buf = chunk
            buf_tokens = chunk_tokens
    if buf:
        merged_chunks.append(buf)
    return merged_chunks
