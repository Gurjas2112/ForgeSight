"""
ForgeSight — RAG retrieval (runtime). Hybrid (vector + full-text) + metadata filter.
Adapted from the provided rag_retrieval.py: plain SQL on doc_chunks (full control over RLS,
scoring, and Citation construction). Used by the Diagnostic pipeline's retrieve_rag and
match_history steps.

Why hybrid + metadata filter (forgesight-v3-final.md §1.7):
  - equipment_id filter BEFORE similarity → a sinter-fan query can't retrieve the caster manual.
  - RRF-style fusion of vector cosine (0.7) + full-text ts_rank (0.3): fault codes / part numbers
    (F0247, SKF 22230) are exact-match tokens embeddings handle poorly.
  - stable sort by id → identical retrievals yield identical prompt prefixes (KV-cache friendly).
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_ollama import OllamaEmbeddings

from backend.config import get_settings
from backend.schemas.agent_models import Citation

_settings = get_settings()
_emb = OllamaEmbeddings(model=_settings.embed_model, base_url=_settings.ollama_host)


@dataclass
class RetrievedChunk:
    id: str
    content: str
    section_ref: str        # → Evidence-chip label + Citation.ref
    doc_type: str
    source: str
    score: float


HYBRID_SQL = """
WITH vec AS (
  SELECT id, content, section_ref, doc_type, source,
         1 - (embedding <=> %(qv)s::vector) AS vscore
  FROM doc_chunks
  WHERE (%(eq)s::text IS NULL OR equipment_id = %(eq)s::text OR equipment_id IS NULL)
    AND (%(dt)s::text[] IS NULL OR doc_type::text = ANY(%(dt)s))
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

# Full-text-only retrieval — used when no embedding backend is reachable (e.g. on Fly.io,
# where on-prem Ollama embeddings aren't available). Keeps citations REAL (chunks come from the
# DB); an ILIKE fallback guarantees exact tokens like fault codes / part numbers still match even
# when websearch_to_tsquery yields no lexemes.
FULLTEXT_SQL = """
SELECT id, content, section_ref, doc_type, source,
       ts_rank(to_tsvector('english', content), websearch_to_tsquery('english', %(q)s)) AS score
FROM doc_chunks
WHERE (%(eq)s::text IS NULL OR equipment_id = %(eq)s::text OR equipment_id IS NULL)
  AND (%(dt)s::text[] IS NULL OR doc_type::text = ANY(%(dt)s))
  AND (to_tsvector('english', content) @@ websearch_to_tsquery('english', %(q)s)
       OR content ILIKE %(like)s OR section_ref ILIKE %(like)s)
ORDER BY score DESC
LIMIT %(k)s;
"""


def _embed_query(query: str) -> str | None:
    """Embed a query for vector search; return None if the embedding backend is unreachable."""
    if _settings.retrieval_mode == "fulltext":
        return None
    try:
        qv = _emb.embed_query(query)
        return "[" + ",".join(f"{x:.6f}" for x in qv) + "]"
    except Exception:  # noqa: BLE001 — any embedding failure → fall back to full-text
        return None


def _doc_type_to_kind(doc_type: str, section_ref: str) -> str:
    if doc_type == "manual":
        return "manual"
    if doc_type == "sop":
        return "sop"
    return "history"          # breakdown 'report' chunks → history citations


def retrieve_rag(conn, query: str, equipment_id: str | None = None,
                 doc_types: list[str] | None = None, k: int = 8) -> list[RetrievedChunk]:
    vec_literal = _embed_query(query)
    with conn.cursor() as cur:
        if vec_literal is None:                       # full-text-only (no cloud embeddings)
            cur.execute(FULLTEXT_SQL, {"eq": equipment_id, "dt": doc_types,
                                       "q": query, "like": f"%{query}%", "k": k})
        else:
            cur.execute(HYBRID_SQL, {"qv": vec_literal, "eq": equipment_id,
                                     "dt": doc_types, "q": query, "k": k})
        rows = cur.fetchall()
    chunks = [RetrievedChunk(str(r[0]), r[1], r[2], r[3], r[4], float(r[5])) for r in rows]
    return sorted(chunks, key=lambda c: c.id)            # stable for prefix/KV cache


def match_history(conn, equipment_id: str, fault_code: str | None = None,
                  symptoms: str | None = None, k: int = 5) -> list[RetrievedChunk]:
    """Similar past breakdowns. Verified records float to the top (green chip)."""
    q = " ".join(x for x in (fault_code, symptoms) if x) or (fault_code or symptoms or "")
    hits = retrieve_rag(conn, q, equipment_id, doc_types=["report"], k=k * 2)
    hits.sort(key=lambda c: (0 if "[VERIFIED]" in c.section_ref else 1, -c.score))
    return hits[:k]


def to_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    """RetrievedChunk → Citation (the ForgeState evidence-chip type). The `ref` is the
    section_ref the citation-existence guardrail validates against."""
    out: list[Citation] = []
    for c in chunks:
        ref = c.section_ref.replace(" [VERIFIED]", "")
        out.append(Citation(kind=_doc_type_to_kind(c.doc_type, c.section_ref),
                            ref=ref, chunk_id=c.id))
    return out
