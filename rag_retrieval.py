"""
ForgeSight — RAG retrieval (runtime). Hybrid (vector + full-text) + metadata filter.
Used by the Diagnostic pipeline's retrieve_rag tool and match_history.
Plain SQL on doc_chunks — full control over RLS, scoring, citation construction.
"""
from __future__ import annotations
from dataclasses import dataclass
from langchain_ollama import OllamaEmbeddings

_emb = OllamaEmbeddings(model="nomic-embed-text")

@dataclass
class RetrievedChunk:
    id: str
    content: str
    section_ref: str        # -> Evidence-chip label + Citation.ref
    doc_type: str
    source: str
    score: float

HYBRID_SQL = """
WITH vec AS (
  SELECT id, content, section_ref, doc_type, source,
         1 - (embedding <=> %(qv)s::vector) AS vscore
  FROM doc_chunks
  WHERE (%(eq)s IS NULL OR equipment_id = %(eq)s OR equipment_id IS NULL)
    AND (%(dt)s IS NULL OR doc_type = ANY(%(dt)s))
  ORDER BY embedding <=> %(qv)s::vector
  LIMIT 20),
kw AS (
  SELECT id, ts_rank(to_tsvector('english', content),
                     websearch_to_tsquery(%(q)s)) AS kscore
  FROM doc_chunks
  WHERE to_tsvector('english', content) @@ websearch_to_tsquery(%(q)s)
    AND (%(eq)s IS NULL OR equipment_id = %(eq)s OR equipment_id IS NULL)
  LIMIT 20)
SELECT v.id, v.content, v.section_ref, v.doc_type, v.source,
       (v.vscore * 0.7 + COALESCE(k.kscore, 0) * 0.3) AS score
FROM vec v LEFT JOIN kw k USING (id)
ORDER BY score DESC
LIMIT %(k)s;
"""

def retrieve_rag(conn, query: str, equipment_id: str | None = None,
                 doc_types: list[str] | None = None, k: int = 8) -> list[RetrievedChunk]:
    qv = _emb.embed_query(query)
    vec_literal = "[" + ",".join(f"{x:.6f}" for x in qv) + "]"
    with conn.cursor() as cur:
        cur.execute(HYBRID_SQL, {"qv": vec_literal, "eq": equipment_id,
                                 "dt": doc_types, "q": query, "k": k})
        rows = cur.fetchall()
    chunks = [RetrievedChunk(*r) for r in rows]
    # stable ordering by id for prompt-prefix / KV cache hit rate
    return sorted(chunks, key=lambda c: c.id)

def match_history(conn, equipment_id: str, fault_code: str | None = None,
                  symptoms: str | None = None, k: int = 5) -> list[RetrievedChunk]:
    """Similar past breakdowns. Verified records float to the top (green chip)."""
    q = symptoms or fault_code or ""
    hits = retrieve_rag(conn, q, equipment_id, doc_types=["report"], k=k * 2)
    hits.sort(key=lambda c: (0 if "[VERIFIED]" in c.section_ref else 1, -c.score))
    return hits[:k]
