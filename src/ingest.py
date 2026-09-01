"""Ingest PDFs from data/ into the configured vector store.

Run:  python -m src.ingest
"""
import re

import pymupdf as fitz

from . import config, utils
from .vectorstore import get_collection


def find_pdfs(data_dir=config.DATA_DIR):
    return sorted(data_dir.glob("*.pdf"))


def _guess_category(name: str) -> str:
    """Choose a useful default category from an official document filename."""
    name = name.lower()
    if any(word in name for word in ("fee", "admission", "brochure")):
        return "admission"
    if any(word in name for word in ("club", "student", "activity")):
        return "student_life"
    if any(word in name for word in ("hostel", "accommodation")):
        return "hostel"
    return "general"


def extract_pages(pdf_path):
    """Yield (page_number, cleaned_text) for each page of a PDF."""
    doc = fitz.open(pdf_path)
    try:
        for i, page in enumerate(doc, start=1):
            text = utils.clean_text(page.get_text())
            if text:
                yield i, text
    finally:
        doc.close()


def _split_long_paragraph(para, target_words):
    """Split an oversized paragraph on sentence boundaries into pieces."""
    if len(para.split()) <= target_words:
        return [para]
    pieces, buf, words = [], [], 0
    for sentence in re.split(r"(?<=[.!?])\s+", para):
        w = len(sentence.split())
        if buf and words + w > target_words:
            pieces.append(" ".join(buf))
            buf, words = [], 0
        buf.append(sentence)
        words += w
    if buf:
        pieces.append(" ".join(buf))
    return pieces


def chunk_text(text, target_words=config.CHUNK_WORDS, overlap_words=30):
    """Paragraph-aware chunking: group paragraphs up to ~target_words."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf, words = [], [], 0
    for para in paragraphs:
        for piece in _split_long_paragraph(para, target_words):
            w = len(piece.split())
            if buf and words + w > target_words:
                chunks.append(" ".join(buf))
                overlap = " ".join(" ".join(buf).split()[-overlap_words:])
                buf, words = ([overlap] if overlap else []), len(overlap.split())
            buf.append(piece)
            words += w
    if buf:
        chunks.append(" ".join(buf))
    return chunks


def ingest_document(pdf_path, collection=None):
    """Extract, chunk, embed and store one PDF. Returns (pages, stored, skipped)."""
    collection = collection or get_collection()
    ids, docs, metas = [], [], []
    pages = 0
    for page_num, text in extract_pages(pdf_path):
        pages += 1
        for chunk in chunk_text(text):
            ids.append(utils.content_hash(chunk))
            docs.append(chunk)
            metas.append({
                "filename": pdf_path.name,
                "doc_type": pdf_path.suffix.lstrip("."),
                "page": page_num,
                "category": _guess_category(pdf_path.name),
            })
    current_ids = set(ids)
    if ids and hasattr(collection, "delete"):
        if hasattr(collection, "get_document_ids"):
            document_ids = collection.get_document_ids(pdf_path.name)
        else:
            document_ids = collection.get(
                where={"filename": pdf_path.name}, include=[]
            )["ids"]
        stale_ids = set(document_ids) - current_ids
        if stale_ids:
            try:
                collection.delete(list(stale_ids))
            except TypeError:
                collection.delete(ids=list(stale_ids))
    existing = set(collection.get(ids=ids, include=[])["ids"]) if ids else set()
    fresh = [(i, d, m) for i, d, m in zip(ids, docs, metas) if i not in existing]
    if fresh:
        collection.add(
            ids=[f[0] for f in fresh],
            documents=[f[1] for f in fresh],
            metadatas=[f[2] for f in fresh],
        )
    return pages, len(fresh), len(ids) - len(fresh)


def main():
    pdfs = find_pdfs()
    if not pdfs:
        print("No PDFs found in data/. Drop college documents there and re-run.")
        return
    print(f"Found {len(pdfs)} PDF(s): {', '.join(p.name for p in pdfs)}")
    collection = get_collection()
    total_pages = total_stored = 0
    for pdf in pdfs:
        pages, stored, skipped = ingest_document(pdf, collection)
        total_pages += pages
        total_stored += stored
        print(f"  {pdf.name}: {pages} pages, {stored} chunks stored, {skipped} skipped (already indexed)")
    print(f"Done. {len(pdfs)} file(s), {total_pages} page(s), {total_stored} new chunk(s) in '{config.COLLECTION}'.")


if __name__ == "__main__":
    main()
