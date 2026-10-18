import os
import re
from openai import OpenAI
from llama_index.readers.file import PDFReader
from llama_index.core.node_parser import SentenceSplitter
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENROUTER_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

client = OpenAI(
    api_key=api_key,
    base_url=base_url,
)
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-large")
EMBED_DIM = int(os.getenv("EMBED_DIM", "3072"))

splitter = SentenceSplitter(chunk_size=1000, chunk_overlap=200)


def extract_section_heading(text: str, default_val: str = "") -> str:
    """Detects section or subsection headings from chunk text."""
    lines = text.split("\n")
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        # Markdown heading style (# Title)
        if line.startswith("#"):
            cleaned = line.lstrip("#").strip()
            if cleaned and len(cleaned) < 80:
                return cleaned
        # Numbered headings (e.g. 1. Introduction, 2.3 System Architecture)
        if re.match(r"^(?:(?:Section|Chapter|\d+(?:\.\d+)*)\s+[A-Za-z0-9][A-Za-z0-9\s:,\-\?]+)$", line, re.IGNORECASE) and len(line) < 80:
            return line
        # All-caps or title-case short headers (e.g. ABSTRACT, EXECUTIVE SUMMARY)
        if re.match(r"^[A-Z][A-Za-z0-9\s:,\-]{2,50}:?$", line) and len(line.split()) <= 6:
            return line
    return default_val


def load_and_chunk_pdf_with_metadata(path: str) -> list[dict]:
    """
    Loads PDF page-by-page, extracts page labels, identifies section/subsection
    headings, and chunks text while retaining provenance metadata.
    """
    docs = PDFReader().load_data(file=path)
    chunks_with_meta = []
    current_section = ""

    for idx, doc in enumerate(docs):
        page_text = getattr(doc, "text", "") or ""
        if not page_text.strip():
            continue

        page_num = str(doc.metadata.get("page_label") or (idx + 1))
        page_heading = extract_section_heading(page_text, current_section)
        if page_heading:
            current_section = page_heading

        page_chunks = splitter.split_text(page_text)
        for chunk in page_chunks:
            chunk_heading = extract_section_heading(chunk, current_section)
            chunks_with_meta.append({
                "text": chunk,
                "page": page_num,
                "section": chunk_heading or f"Page {page_num}",
            })

    return chunks_with_meta


def load_and_chunk_pdf(path: str) -> list[str]:
    chunks_meta = load_and_chunk_pdf_with_metadata(path)
    return [c["text"] for c in chunks_meta]


def embed_texts(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]