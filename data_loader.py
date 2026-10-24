import os
import re
import time
import logging
import httpx
from openai import OpenAI
from llama_index.readers.file import PDFReader
from llama_index.core.node_parser import SentenceSplitter
from dotenv import load_dotenv

try:
    import docx
except ImportError:
    docx = None

try:
    import docx2txt
except ImportError:
    docx2txt = None

load_dotenv()
logger = logging.getLogger("uvicorn")

api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENROUTER_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

# Dedicated HTTP transport with explicit connect, read, and write timeouts
# to prevent "ssl.SSLError: The write operation timed out" during batch uploads.
http_client = httpx.Client(
    timeout=httpx.Timeout(connect=15.0, read=90.0, write=90.0, pool=60.0),
    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
)

client = OpenAI(
    api_key=api_key,
    base_url=base_url,
    http_client=http_client,
    max_retries=3,
)
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-large")
EMBED_DIM = int(os.getenv("EMBED_DIM", "3072"))

# Google Gemini Free Tier Embeddings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "models/gemini-embedding-001")

splitter = SentenceSplitter(chunk_size=1000, chunk_overlap=200)


def extract_section_heading(text: str, default_val: str = "") -> str:
    """Detects section, subsection, or topic headings from text."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return default_val

    for line in lines:
        # Markdown heading style (# Title)
        if line.startswith("#"):
            cleaned = line.lstrip("#").strip()
            if cleaned and len(cleaned) < 80:
                return cleaned
        # Numbered headings (e.g. 1. Introduction, 2.3 System Architecture)
        if re.match(r"^(?:(?:Section|Chapter|\d+(?:\.\d+)*)\s+[A-Za-z0-9][A-Za-z0-9\s:,\-\?]+)$", line, re.IGNORECASE) and len(line) < 80:
            return line
        # Title case / All-caps short headers
        if re.match(r"^[A-Z][A-Za-z0-9\s:,\-]{2,50}:?$", line) and len(line.split()) <= 7:
            return line

    # Fallback to the first line if it looks like a slide or section header (< 60 chars and not a sentence)
    if lines and len(lines[0]) <= 60 and not lines[0].endswith("."):
        return lines[0]

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
                "section": chunk_heading or current_section or f"Page {page_num}",
            })

    return chunks_with_meta


def load_and_chunk_pdf(path: str) -> list[str]:
    chunks_meta = load_and_chunk_pdf_with_metadata(path)
    return [c["text"] for c in chunks_meta]


def load_and_chunk_docx_with_metadata(path: str) -> list[dict]:
    """
    Loads a Word document (.docx / .doc), extracts structured paragraphs,
    headings, and tables while preserving section provenance and estimating page breaks.
    """
    chunks_with_meta = []
    current_section = ""
    word_count = 0

    if docx is not None:
        try:
            doc = docx.Document(path)

            # 1. Process paragraphs
            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue

                # Check if this paragraph is a styled heading or markdown/numbered heading
                style_name = getattr(para.style, "name", "") or ""
                if style_name.startswith("Heading") or style_name in ("Title", "Subtitle"):
                    current_section = text
                else:
                    heading_candidate = extract_section_heading(text, current_section)
                    if heading_candidate and heading_candidate != current_section:
                        current_section = heading_candidate

                # Word-count-based estimated page number (~350 words per standard printed page)
                para_words = len(text.split())
                word_count += para_words
                page_num = str(max(1, (word_count // 350) + 1))

                para_chunks = splitter.split_text(text)
                for chunk in para_chunks:
                    chunk_heading = extract_section_heading(chunk, current_section)
                    chunks_with_meta.append({
                        "text": chunk,
                        "page": page_num,
                        "section": chunk_heading or current_section or f"Section {page_num}",
                    })

            # 2. Process tables and format them as Markdown
            for t_idx, table in enumerate(doc.tables):
                table_lines = []
                for row_idx, row in enumerate(table.rows):
                    row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                    table_lines.append("| " + " | ".join(row_cells) + " |")
                    # Insert markdown divider after header row
                    if row_idx == 0:
                        table_lines.append("| " + " | ".join(["---"] * len(row_cells)) + " |")

                if table_lines:
                    table_text = f"### Table {t_idx + 1} ({current_section or 'Data'})\n" + "\n".join(table_lines)
                    page_num = str(max(1, (word_count // 350) + 1))
                    chunks_with_meta.append({
                        "text": table_text,
                        "page": page_num,
                        "section": current_section or f"Table {t_idx + 1}",
                    })

            if chunks_with_meta:
                return chunks_with_meta
        except Exception as docx_err:
            logger.warning(f"[Loader] python-docx parsing failed on {path}: {docx_err}. Attempting docx2txt fallback...")

    # Fallback to docx2txt for legacy or corrupted docx
    if docx2txt is not None:
        try:
            raw_text = docx2txt.process(path)
            if raw_text and raw_text.strip():
                lines = raw_text.split("\n\n")
                running_words = 0
                sec = ""
                for line in lines:
                    cleaned = line.strip()
                    if not cleaned:
                        continue
                    sec_cand = extract_section_heading(cleaned, sec)
                    if sec_cand:
                        sec = sec_cand
                    running_words += len(cleaned.split())
                    page_num = str(max(1, (running_words // 350) + 1))
                    for chunk in splitter.split_text(cleaned):
                        chunks_with_meta.append({
                            "text": chunk,
                            "page": page_num,
                            "section": sec or f"Section {page_num}",
                        })
                return chunks_with_meta
        except Exception as txt_err:
            logger.error(f"[Loader] docx2txt fallback failed on {path}: {txt_err}")

    return chunks_with_meta


def load_and_chunk_txt_with_metadata(path: str) -> list[dict]:
    """Loads plain text or Markdown files with line/heading tracking."""
    chunks_with_meta = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if not content.strip():
        return []

    lines = content.split("\n\n")
    running_words = 0
    current_sec = ""
    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue
        sec_cand = extract_section_heading(cleaned, current_sec)
        if sec_cand:
            current_sec = sec_cand
        running_words += len(cleaned.split())
        page_num = str(max(1, (running_words // 350) + 1))
        for chunk in splitter.split_text(cleaned):
            chunks_with_meta.append({
                "text": chunk,
                "page": page_num,
                "section": current_sec or f"Section {page_num}",
            })
    return chunks_with_meta


def load_and_chunk_document_with_metadata(path: str) -> list[dict]:
    """Dispatches to the optimal parser based on file extension (.pdf, .docx, .doc, .txt, .md)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".docx", ".doc"):
        return load_and_chunk_docx_with_metadata(path)
    elif ext in (".txt", ".md"):
        return load_and_chunk_txt_with_metadata(path)
    else:
        return load_and_chunk_pdf_with_metadata(path)


def load_and_chunk_document(path: str) -> list[str]:
    chunks_meta = load_and_chunk_document_with_metadata(path)
    return [c["text"] for c in chunks_meta]


def create_dynamic_batches(
    texts: list[str],
    max_batch_size: int = 15,
    max_batch_chars: int = 12000,
) -> list[list[str]]:
    """
    Groups chunks into dynamically sized batches considering both chunk count
    and total character length.

    - For small PDFs (1-5 pages): Packages all chunks in 1-2 rapid requests.
    - For massive PDFs (100-500+ pages): Bounds payload size strictly below ~12KB
      so that SSL write buffers never stall or time out.
    """
    batches = []
    current_batch = []
    current_chars = 0

    for text in texts:
        text_len = len(text)
        # Flush batch if count limit reached OR adding this chunk exceeds character limit
        if current_batch and (
            len(current_batch) >= max_batch_size or
            (current_chars + text_len) > max_batch_chars
        ):
            batches.append(current_batch)
            current_batch = []
            current_chars = 0

        current_batch.append(text)
        current_chars += text_len

    if current_batch:
        batches.append(current_batch)

    return batches


def _embed_gemini_batch(batch: list[str]) -> list[list[float]]:
    """Generates 3072-dim embeddings using Google Gemini's batchEmbedContents endpoint (Free Tier)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_EMBED_MODEL}:batchEmbedContents?key={GEMINI_API_KEY}"
    requests_payload = [
        {"model": GEMINI_EMBED_MODEL, "content": {"parts": [{"text": t}]}}
        for t in batch
    ]
    resp = http_client.post(url, json={"requests": requests_payload})
    resp.raise_for_status()
    data = resp.json()
    return [item["values"] for item in data["embeddings"]]


def _embed_single_batch(batch: list[str]) -> list[list[float]]:
    """Sends a single embedding request to Gemini (or fallback provider)."""
    if GEMINI_API_KEY:
        try:
            return _embed_gemini_batch(batch)
        except Exception as gemini_err:
            logger.warning(f"[Embeddings] Gemini batch embedding error: {gemini_err}. Attempting fallback...")
            if not api_key:
                raise gemini_err

    # Fallback to OpenAI / OpenRouter client if Gemini is unavailable
    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=batch,
    )
    return [item.embedding for item in response.data]


def _embed_batch_adaptive(batch: list[str], max_retries: int = 3) -> list[list[float]]:
    """
    Attempts to embed a batch with exponential backoff on write timeouts or network glitches.
    If a batch persistently fails, adaptively halves the batch size and embeds recursively.
    """
    last_err = None
    for attempt in range(max_retries):
        try:
            return _embed_single_batch(batch)
        except Exception as e:
            last_err = e
            logger.warning(
                f"[Embeddings] Batch attempt {attempt + 1}/{max_retries} failed ({len(batch)} chunks, "
                f"{sum(len(t) for t in batch)} chars): {e}"
            )
            if attempt < max_retries - 1:
                # Exponential backoff: 1.5s, 3.0s...
                time.sleep(1.5 * (attempt + 1))

    # If all retries failed and batch has more than 1 chunk, adaptively split in half!
    if len(batch) > 1:
        mid = len(batch) // 2
        logger.info(
            f"[Embeddings] Adaptive backoff: Splitting failing batch of {len(batch)} chunks "
            f"into sub-batches of {mid} and {len(batch) - mid}."
        )
        left = _embed_batch_adaptive(batch[:mid], max_retries=2)
        right = _embed_batch_adaptive(batch[mid:], max_retries=2)
        return left + right

    raise last_err


def embed_texts(
    texts: list[str],
    max_batch_size: int = 15,
    max_batch_chars: int = 12000,
) -> list[list[float]]:
    """
    Computes vector embeddings using dynamic character-aware batching
    and adaptive retry fallbacks.

    Accommodates documents of all sizes (from 1-page receipts to 500+ page books)
    without triggering 'The write operation timed out' or Render RAM exhaustion.
    """
    if not texts:
        return []

    batches = create_dynamic_batches(texts, max_batch_size, max_batch_chars)
    logger.info(f"[Embeddings] Processing {len(texts)} chunks across {len(batches)} dynamic batches.")

    all_embeddings = []
    for idx, batch in enumerate(batches):
        batch_vecs = _embed_batch_adaptive(batch)
        all_embeddings.extend(batch_vecs)

        # Cooperative timeslice between batches to release CPU & socket buffers
        if idx + 1 < len(batches):
            time.sleep(0.04)

    return all_embeddings