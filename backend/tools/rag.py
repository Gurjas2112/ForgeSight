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

import re
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


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]+")
# Conversational filler that carries no retrieval signal — dropped so the full-text query keys on
# the distinctive tokens (fault codes, part numbers, equipment/component words) instead.
_STOP = {
    "the", "and", "for", "that", "with", "this", "when", "from", "into", "your", "you", "are",
    "was", "has", "have", "can", "could", "would", "should", "will", "diagnose", "diagnosis",
    "show", "shows", "showing", "rising", "cite", "prior", "past", "record", "records", "please",
    "help", "what", "how", "why", "check", "checking", "tell", "give", "about", "issue", "problem",
    "root", "cause", "causes", "trip", "trips", "tripped", "tripping", "fault", "faults",
}


def _fts_terms(query: str) -> tuple[str, str]:
    """Turn a free-text question into (tsquery, ilike) for the embedding-less full-text path.

    Natural-language questions ("Diagnose the F3 stand — it tripped on fault 0247 …") fail under
    `websearch_to_tsquery`'s implicit AND because no single chunk contains every word. We keep only
    the distinctive tokens (anything with a digit or hyphen — fault codes / part numbers — plus
    content words) and OR them, and we anchor the ILIKE on the most specific token (a code if one is
    present). This keeps citations REAL (still pure DB retrieval) while surviving on Railway, which
    has no GPU embeddings.
    """
    toks = _TOKEN_RE.findall(query or "")
    distinctive = [
        t for t in toks
        if any(ch.isdigit() for ch in t) or "-" in t
        or (len(t) > 3 and t.lower() not in _STOP)
    ]
    keep = list(dict.fromkeys(distinctive)) or list(dict.fromkeys(toks))
    if not keep:
        return query, f"%{query}%"
    tsquery = " OR ".join(keep)
    coded = [t for t in keep if any(ch.isdigit() for ch in t)]
    specific = max(coded, key=len) if coded else max(keep, key=len)
    return tsquery, f"%{specific}%"


def _doc_type_to_kind(doc_type: str, section_ref: str) -> str:
    if doc_type == "manual":
        return "manual"
    if doc_type == "sop":
        return "sop"
    return "history"          # breakdown 'report' chunks → history citations


def retrieve_rag(conn, query: str, equipment_id: str | None = None,
                 doc_types: list[str] | None = None, k: int = 8) -> list[RetrievedChunk]:
    vec_literal = _embed_query(query)
    ts_query, like = _fts_terms(query)
    with conn.cursor() as cur:
        if vec_literal is None:                       # full-text-only (no cloud embeddings)
            cur.execute(FULLTEXT_SQL, {"eq": equipment_id, "dt": doc_types,
                                       "q": ts_query, "like": like, "k": k})
        else:
            cur.execute(HYBRID_SQL, {"qv": vec_literal, "eq": equipment_id,
                                     "dt": doc_types, "q": ts_query, "k": k})
        rows = cur.fetchall()
    chunks = [RetrievedChunk(str(r[0]), r[1], r[2], r[3], r[4], float(r[5])) for r in rows]
    return sorted(chunks, key=lambda c: c.id)            # stable for prefix/KV cache


def apply_feedback_ranking(hits: list[RetrievedChunk], equipment_id: str | None,
                           fault_code: str | None) -> list[RetrievedChunk]:
    """FR-6 re-ranking: verified records float up; engineer-down-voted records sink. A pure
    function of the hit list + the feedback store so it is unit-testable without a DB."""
    from backend.tools import feedback_store as fb

    demoted = fb.demoted_refs(equipment_id, fault_code)
    group_penalty = fb.penalty_for(equipment_id, fault_code)
    # A group down-vote with no explicit ref demotes the current top record (the one shown).
    if group_penalty and not demoted and hits:
        top = sorted(hits, key=lambda c: (0 if "[VERIFIED]" in c.section_ref else 1, -c.score))[0]
        demoted = {top.section_ref.replace(" [VERIFIED]", "")}

    def _rank(c: RetrievedChunk):
        ref = c.section_ref.replace(" [VERIFIED]", "")
        penalised = 1 if ref in demoted else 0           # primary: down-voted sinks to the bottom
        verified = 0 if "[VERIFIED]" in c.section_ref else 1
        return (penalised, verified, -c.score)

    return sorted(hits, key=_rank)


def match_history(conn, equipment_id: str, fault_code: str | None = None,
                  symptoms: str | None = None, k: int = 5) -> list[RetrievedChunk]:
    """Similar past breakdowns. Verified records float to the top (green chip); feedback
    conditioning (down-votes) demotes records on subsequent asks."""
    q = " ".join(x for x in (fault_code, symptoms) if x) or (fault_code or symptoms or "")
    hits = retrieve_rag(conn, q, equipment_id, doc_types=["report"], k=k * 2)
    hits = apply_feedback_ranking(hits, equipment_id, fault_code)
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
