"""
ForgeSight — SLM synthesis adapter (Ollama, constrained decoding).
==================================================================
Implements the `llm` interface the AgentController depends on:
  - classify(text, equipment_id)              → (intent, query_class)
  - synthesize_card(intent, tool_results, …)  → card dict
  - synthesize_card_with_errors(previous, …)  → repaired card dict

The SLM is invoked ONLY here (synthesis/repair) and at classify — never to select tools or
compute numbers. `format=<json schema>` makes schema-invalid JSON structurally impossible
(ollama.com/blog/structured-outputs); the fine-tune buys semantic quality. Base Qwen2.5-3B is
the Pass-1 runtime model (the design's sanctioned fallback until the fine-tune promotes).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import ollama
from pydantic import BaseModel

from backend.agent.prompt_builder import build_context
from backend.config import get_settings
from backend.schemas.cards import (
    ChecklistCard, DiagnosisCard, NoEvidenceCard, PriorityCard, RiskCard,
    RULEstimate, SparesCard, WaitAssessmentCard,
)

# intent → the card schema the SLM must fill (constrained-decode target).
INTENT_CARD: dict[str, type[BaseModel]] = {
    "diagnosis": DiagnosisCard,
    "sop_lookup": ChecklistCard,
    "health_query": RiskCard,
    "rul_query": RULEstimate,
    "defect_query": RiskCard,
    "priority_query": PriorityCard,
    "spares_query": SparesCard,
    "wait_assessment": WaitAssessmentCard,
}

INTENTS = list(INTENT_CARD) + ["report_request", "analytical_query"]
QUERY_CLASSES = ["knowledge", "live_status", "action"]
CITATION_REQUIRED_INTENTS = {"diagnosis", "sop_lookup", "health_query", "wait_assessment"}

DIAGNOSTIC_PERSONA = (
    "You are the Diagnostic Agent for a steel plant maintenance system. You diagnose equipment "
    "faults and identify root causes using ONLY the provided CITATIONS and TOOL_RESULTS. Every "
    "claim must be supported by a citation ref that appears in CITATIONS. Rank root causes. "
    "Express confidence as High/Medium/Low, never percentages. Copy every number verbatim from "
    "TOOL_RESULTS — never invent or recompute. If CITATIONS is empty or irrelevant, you MUST "
    "refuse with a no_evidence card. Output ONLY the JSON card."
)

_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "query_class": {"type": "string", "enum": QUERY_CLASSES},
    },
    "required": ["intent", "query_class"],
    "additionalProperties": False,
}


class OllamaSynthesizer:
    """Concrete `llm` passed to AgentController.

    Backend is selected by `SYNTHESIS_BACKEND`:
      - "ollama" (default): on-prem Qwen2.5-3B via Ollama, constrained decoding (citation
        compliance is STRUCTURAL — the grammar can only emit retrieved refs).
      - "hosted": a cloud LLM API (Groq or OpenAI, OpenAI-compatible SDK) for deployments
        where Ollama isn't reachable (Railway). Same prompts + JSON schema; citation
        compliance is instruction-enforced and still re-checked by the downstream guardrail.
    The class name is kept for backwards-compat with build_controller wiring.
    """

    def __init__(self, model: str | None = None, host: str | None = None, pool=None):
        s = get_settings()
        self._pool = pool                 # for token-usage logging + LLM response cache (None in scripts)
        self._backend = s.synthesis_backend
        if self._backend == "hosted":
            from openai import OpenAI  # lazy: Groq + OpenAI both use this SDK
            base = s.hosted_llm_base_url()
            self._openai = OpenAI(api_key=s.llm_api_key, base_url=base) if base else OpenAI(
                api_key=s.llm_api_key)
            self.model = model or s.llm_model
        else:
            self.model = model or s.ollama_model
            self._client = ollama.Client(host=host or s.ollama_host)

    # ---- T1: intent + query-class classification --------------------------------------
    def classify(self, text: str, equipment_id: str | None) -> tuple[str, str]:
        sys_msg = (
            "Classify the maintenance query. intent ∈ " + ", ".join(INTENTS) + ". "
            "Use 'analytical_query' for questions that COUNT or AGGREGATE over records/logs "
            "(how many, most common root cause, total downtime, list/most/which across equipment). "
            "query_class: 'knowledge' (manuals/SOPs/diagnosis), 'live_status' (current health/RUL/"
            "sensors), or 'action' (reserve/order/report). Output only JSON."
        )
        user = (f"EQUIPMENT: {equipment_id or '(none)'}\nUSER QUERY: {text}")
        data = self._chat_json(_CLASSIFY_SCHEMA, sys_msg, user, temperature=0, call_type="classify")
        intent = data.get("intent") if data.get("intent") in INTENTS else "diagnosis"
        qclass = data.get("query_class") if data.get("query_class") in QUERY_CLASSES else "knowledge"
        return intent, qclass

    # ---- T2–T8: card synthesis --------------------------------------------------------
    def synthesize_card(self, *, intent: str, tool_results: dict[str, Any],
                        citations: list[dict], history: Any = None) -> dict:
        card_model = INTENT_CARD.get(intent, DiagnosisCard)
        cite_excerpts = _citation_excerpts(tool_results, citations)

        # Hard refusal gate (also enforced by the guardrail): no evidence → no_evidence card.
        if intent in CITATION_REQUIRED_INTENTS and not cite_excerpts:
            return NoEvidenceCard().model_dump()

        context = build_context(
            equipment=_equipment_from_results(tool_results),
            tool_results=_slim_tool_results(tool_results),
            citations=cite_excerpts,
            user_query=_query_from_history(history) or "(see context)",
            history=_summarize_history(history),
        )
        # FR-6 — inject engineer-confirmed fixes for this (equipment, fault) as few-shot exemplars
        # so a 'fixed' verdict measurably steers the next diagnosis toward the verified cause.
        exemplars = _exemplar_block(tool_results)
        if exemplars:
            context += exemplars
        allowed = [c["ref"] for c in cite_excerpts]
        instruction = (
            f"\n\nProduce a single {card_model.__name__} JSON object. "
            "The `citation_refs` field MUST be a NON-EMPTY list containing one or more of EXACTLY "
            f"these ref strings, copied verbatim: {json.dumps(allowed, ensure_ascii=False)}. "
            "Never invent a ref. Every ranked root_cause's citation_refs must also use only those "
            "strings. Copy all numbers from TOOL_RESULTS verbatim. Safety/LOTO steps come FIRST."
        )
        return self._fill(card_model, DIAGNOSTIC_PERSONA, context + instruction,
                          allowed_refs=allowed, call_type="synthesize")

    # ---- T9: repair (retry-once with the violation list as feedback) ------------------
    def synthesize_card_with_errors(self, *, previous: dict, violations: list[str],
                                    tool_results: dict[str, Any], citations: list[dict]) -> dict:
        card_type = previous.get("card_type", "diagnosis")
        card_model = next((m for m in INTENT_CARD.values()
                           if getattr(m.model_fields.get("card_type"), "default", None) == card_type),
                          DiagnosisCard)
        cite_excerpts = _citation_excerpts(tool_results, citations)
        allowed = [c["ref"] for c in cite_excerpts]
        user = (
            "Your previous card FAILED validation. Fix EXACTLY these violations and return a "
            "corrected card of the same type.\n\n"
            f"VIOLATIONS: {json.dumps(violations)}\n\n"
            f"PREVIOUS_CARD: {json.dumps(previous, default=str)}\n\n"
            f"{build_context(equipment=_equipment_from_results(tool_results), tool_results=_slim_tool_results(tool_results), citations=cite_excerpts, user_query='(repair)')}"
            "\n\nReturn ONLY the corrected JSON card. `citation_refs` MUST be a NON-EMPTY list "
            f"using ONLY these exact strings: {json.dumps(allowed, ensure_ascii=False)}. "
            "Copy numbers from TOOL_RESULTS; LOTO/safety steps first."
        )
        return self._fill(card_model, DIAGNOSTIC_PERSONA, user, allowed_refs=allowed,
                          call_type="repair")

    # ---- shared constrained-decode call ----------------------------------------------
    def _fill(self, card_model: type[BaseModel], system: str, user: str,
              allowed_refs: list[str] | None = None, call_type: str = "synthesize") -> dict:
        schema = card_model.model_json_schema()
        if allowed_refs:
            # Constrained decoding makes citation compliance STRUCTURAL, not advisory: the
            # decoder may only emit citation_refs drawn from the retrieved set, ≥1 of them.
            # This is the design's "schema-invalid output is impossible" principle applied to
            # the anti-hallucination gate — base Qwen-3B then cannot omit or fabricate a ref.
            schema = _constrain_citation_refs(schema, allowed_refs)
        data = self._chat_json(schema, system, user, temperature=0.1, call_type=call_type)
        default_ct = getattr(card_model.model_fields.get("card_type"), "default", None)
        if default_ct and not data.get("card_type"):
            data["card_type"] = default_ct
        return data

    # ---- backend-agnostic constrained JSON chat (with response cache + token metering) ----
    def _chat_json(self, schema: dict, system: str, user: str, *, temperature: float,
                   call_type: str = "synthesize") -> dict:
        """One JSON-schema-constrained chat turn, dispatched to the configured backend.

        A persistent LLM response cache (llm_cache, keyed by backend|model|system|user) is checked
        first: a hit returns the stored card and spends ZERO tokens. On a miss we call the model,
        record token usage (llm_usage), and store the response. Both the cache and the meter are
        best-effort — a DB hiccup never breaks synthesis (it just runs uncached/unmetered)."""
        key = _cache_key(self._backend, self.model, system, user)
        cached = self._cache_get(key)
        if cached:
            self._record_usage(call_type, 0, 0, 0, cached=True)
            return cached

        if self._backend == "hosted":
            data, usage = self._openai_chat_json(schema, system, user, temperature)
        else:
            data, usage = self._ollama_chat_json(schema, system, user, temperature)

        self._record_usage(call_type, *usage, cached=False)
        if data:                                  # never cache an empty/failed parse
            self._cache_put(key, data, call_type)
        return data

    def _ollama_chat_json(self, schema, system, user, temperature) -> tuple[dict, tuple[int, int, int]]:
        resp = self._client.chat(
            model=self.model, format=schema, options={"temperature": temperature},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        p = int(resp.get("prompt_eval_count") or 0)
        c = int(resp.get("eval_count") or 0)
        return _loads(resp["message"]["content"]), (p, c, p + c)

    def _openai_chat_json(self, schema, system, user, temperature) -> tuple[dict, tuple[int, int, int]]:
        """Hosted API fallback (Groq/OpenAI via OpenAI-compatible SDK). JSON mode + schema-in-prompt;
        the enum-constrained `citation_refs` is described to the model and the downstream
        guardrail still validates ref existence."""
        sys_msg = (system + "\n\nReturn ONLY a JSON object that conforms to this JSON Schema:\n"
                   + json.dumps(schema, ensure_ascii=False))
        resp = self._openai.chat.completions.create(
            model=self.model, temperature=temperature,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": sys_msg},
                      {"role": "user", "content": user}],
        )
        u = getattr(resp, "usage", None)
        usage = ((getattr(u, "prompt_tokens", 0) or 0), (getattr(u, "completion_tokens", 0) or 0),
                 (getattr(u, "total_tokens", 0) or 0)) if u else (0, 0, 0)
        return _loads(resp.choices[0].message.content or ""), usage

    # ---- token-usage meter + response cache (best-effort, pool-gated) -----------------
    def _cache_get(self, key: str) -> dict | None:
        if not self._pool:
            return None
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute("UPDATE llm_cache SET hits = hits + 1, last_hit_at = now() "
                            "WHERE cache_key = %s RETURNING response", (key,))
                row = cur.fetchone()
                return row[0] if row else None
        except Exception:  # noqa: BLE001
            return None

    def _cache_put(self, key: str, data: dict, call_type: str) -> None:
        if not self._pool:
            return
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute("INSERT INTO llm_cache (cache_key, response, model, call_type) "
                            "VALUES (%s, %s::jsonb, %s, %s) ON CONFLICT (cache_key) DO NOTHING",
                            (key, json.dumps(data, default=str), self.model, call_type))
        except Exception:  # noqa: BLE001
            pass

    def _record_usage(self, call_type: str, prompt: int, completion: int, total: int,
                      *, cached: bool) -> None:
        if not self._pool:
            return
        try:
            with self._pool.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO llm_usage (backend, model, call_type, prompt_tokens, "
                    "completion_tokens, total_tokens, cached) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (self._backend, self.model, call_type, prompt, completion, total, cached))
        except Exception:  # noqa: BLE001
            pass


def _cache_key(backend: str, model: str, system: str, user: str) -> str:
    """Stable key for the LLM response cache. Identical (backend, model, prompt) → same answer,
    so the same query+evidence is served from cache and spends no tokens; when live numbers in
    the prompt change, the key changes and the cache correctly misses."""
    return hashlib.sha256(f"{backend}|{model}|{system}|{user}".encode("utf-8")).hexdigest()


def _constrain_citation_refs(schema: dict, allowed: list[str]) -> dict:
    """Inject `enum`=allowed + minItems=1 into every citation_refs array in the schema
    (top-level card + nested $defs like RootCause), and require it on the top-level card.
    Ollama compiles this to a GBNF grammar → the SLM cannot emit an invalid/empty ref list."""
    ref_array = {"type": "array", "items": {"type": "string", "enum": allowed}, "minItems": 1}

    def _patch(obj: dict) -> None:
        props = obj.get("properties")
        if isinstance(props, dict) and "citation_refs" in props:
            props["citation_refs"] = dict(ref_array)
            req = obj.setdefault("required", [])
            if "citation_refs" not in req:
                req.append("citation_refs")

    _patch(schema)
    for d in (schema.get("$defs") or {}).values():
        if isinstance(d, dict):
            _patch(d)
    return schema


# ---------------------------------------------------------------------------------------
# helpers — turn the pipeline's tool_results into prompt-ready citation excerpts
# ---------------------------------------------------------------------------------------

def _citation_excerpts(tool_results: dict[str, Any], citations: list[dict]) -> list[dict]:
    """Build [{ref, excerpt}] from the retrieved chunks the pipeline stashed in tool_results.
    Only refs that are present in `citations` (i.e. actually retrieved) are eligible."""
    known_refs = {c.get("ref") for c in (citations or [])}
    out: list[dict] = []
    seen: set[str] = set()
    for key in ("retrieve_rag", "match_history"):
        for item in tool_results.get(key, []) or []:
            ref = item.get("ref")
            if ref and ref in known_refs and ref not in seen:
                out.append({"ref": ref, "excerpt": item.get("excerpt", "")})
                seen.add(ref)
    # any citation without an excerpt still gets listed (ref-only) so it can be cited
    for c in citations or []:
        if c.get("ref") and c["ref"] not in seen:
            out.append({"ref": c["ref"], "excerpt": ""})
            seen.add(c["ref"])
    return out


def _slim_tool_results(tool_results: dict[str, Any]) -> dict[str, Any]:
    """Drop bulky chunk text from TOOL_RESULTS (it's already in CITATIONS); keep numeric/struct."""
    slim: dict[str, Any] = {}
    for k, v in tool_results.items():
        if k in ("retrieve_rag", "match_history"):
            slim[k] = [{"ref": i.get("ref"), "fault_code": i.get("fault_code")}
                       for i in (v or []) if isinstance(i, dict)]
        else:
            slim[k] = v
    return slim


def _equipment_from_results(tool_results: dict[str, Any]) -> dict | None:
    return tool_results.get("_equipment")


def _fault_from_results(tool_results: dict[str, Any]) -> str | None:
    for item in tool_results.get("match_history", []) or []:
        if isinstance(item, dict) and item.get("fault_code"):
            return item["fault_code"]
    return None


def _exemplar_block(tool_results: dict[str, Any]) -> str:
    """Render engineer-confirmed (VERIFIED) fixes for this equipment+fault as a few-shot block.
    Returns '' when there is no feedback yet (so the prompt is unchanged on a cold system)."""
    from backend.tools import feedback_store as fb

    eq = (_equipment_from_results(tool_results) or {}).get("id")
    fault = _fault_from_results(tool_results)
    exemplars = fb.exemplars_for(eq, fault)
    if not exemplars:
        return ""
    lines = ["\n\nENGINEER-VERIFIED FIXES (confirmed on this equipment+fault — prefer these "
             "as the leading root cause):"]
    for e in exemplars[-3:]:
        rc = (e.get("root_cause") or "").strip()
        fx = (e.get("fix") or "").strip()
        lines.append(f"- root_cause: {rc}" + (f" · fix: {fx}" if fx else ""))
    return "\n".join(lines)


def _query_from_history(history: Any) -> str | None:
    if not history:
        return None
    for m in reversed(history):
        role = getattr(m, "type", None) or getattr(m, "role", None) or (
            m.get("role") if isinstance(m, dict) else None)
        if role in ("human", "user"):
            content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else None)
            return content if isinstance(content, str) else None
    return None


def _summarize_history(history: Any) -> str | None:
    if not history or len(history) <= 1:
        return None
    turns = []
    for m in history[-4:]:
        role = getattr(m, "type", None) or getattr(m, "role", None) or (
            m.get("role") if isinstance(m, dict) else "")
        content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else "")
        if isinstance(content, str) and content:
            turns.append(f"{role}: {content[:120]}")
    return " | ".join(turns) if turns else None


def _loads(content: str) -> dict:
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {}
