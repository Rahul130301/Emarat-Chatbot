# build/chunk_and_store_documents.py
import os
import re
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from azure.cosmos import PartitionKey
from db import get_connection
from cosmos_catalog_db import get_cosmos_database
from embedding_utils import embed

EMBEDDING_DIMENSIONS = 3072
CHUNK_WORD_LIMIT = 600
CHUNK_OVERLAP_WORDS = 80

HEADER_RE = re.compile(r'^(#{1,6})\s+(.*)$', re.MULTILINE)


def _create_container():
    db = get_cosmos_database()
    return db.create_container_if_not_exists(
        id="contract_document_chunks",
        partition_key=PartitionKey(path="/contract_id"),
        indexing_policy={
            "indexingMode": "consistent",
            "automatic": True,
            "includedPaths": [{"path": "/*"}],
            "excludedPaths": [{"path": "/embedding/*"}, {"path": "/\"_etag\"/?"}],
            "vectorIndexes": [{"path": "/embedding", "type": "quantizedFlat"}],
        },
        vector_embedding_policy={
            "vectorEmbeddings": [
                {"path": "/embedding", "dataType": "float32",
                 "distanceFunction": "cosine", "dimensions": EMBEDDING_DIMENSIONS}
            ]
        },
    )


def split_by_headers(markdown_text: str):
    """Splits on markdown # headers. Returns (level, title, content) tuples."""
    matches = list(HEADER_RE.finditer(markdown_text))
    if not matches:
        return [(0, "Full Document", markdown_text)]
    sections = []
    if matches[0].start() > 0:
        preamble = markdown_text[:matches[0].start()].strip()
        if preamble:
            sections.append((0, "Preamble", preamble))
    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
        content = markdown_text[start:end].strip()
        if content:
            sections.append((level, title, content))
    return sections


def sub_chunk(text: str, limit=CHUNK_WORD_LIMIT, overlap=CHUNK_OVERLAP_WORDS):
    words = text.split()
    if len(words) <= limit:
        return [text]
    chunks, start = [], 0
    while start < len(words):
        end = start + limit
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap
    return chunks


def chunk_document(contract_id: str, document_name: str, full_markdown: str):
    docs, chunk_index = [], 0
    for level, title, content in split_by_headers(full_markdown):
        for piece in sub_chunk(content):
            docs.append({
                "id": f"{contract_id}:{chunk_index}",
                "contract_id": contract_id,
                "document_name": document_name,
                "section_title": title,
                "section_level": level,
                "chunk_index": chunk_index,
                "chunk_text": piece,
            })
            chunk_index += 1
    return docs


def main():
    container = _create_container()
    conn = get_connection(database="contract-warehouse")
    with conn.cursor() as cur:
        cur.execute("SELECT contract_id, document_name, full_markdown FROM contract_documents")
        rows = cur.fetchall()
    conn.close()

    total_chunks = 0
    for contract_id, document_name, full_markdown in rows:
        if not full_markdown:
            continue
        chunks = chunk_document(contract_id, document_name, full_markdown)
        for c in chunks:
            c["embedding"] = embed(f"{c['section_title']}: {c['chunk_text']}")
            container.upsert_item(c)
        total_chunks += len(chunks)
        print(f"{document_name} ({contract_id}): {len(chunks)} chunks")
    print(f"Total chunks stored: {total_chunks}")


if __name__ == "__main__":
    main()