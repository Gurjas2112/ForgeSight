# ForgeSight v3 — FINAL Hackathon Project Pipeline & Full-Stack Architecture
### Intelligent Maintenance Wizard · Tata Steel AI Hackathon 2026 (HackerEarth)
**Supersedes all prior drafts.** Consolidates everything agreed across planning: two-human role model, governed multi-agent architecture (Authority · Controller · Guardrails · State), **SLM-first runtime** (the fine-tuned Qwen carries all runtime LLM duties; hosted models are dev-time/fallback only — PS FR-1 explicitly permits SLM-only and APIs are optional), persistent timestamped chat sessions, full caching/observability stack, authentication + validation + verification, scenario-driven UX, and complete PS §4–§9 traceability.

---

## 0. The winning thesis

Judged by Tata Steel industry leaders, scored on "translating AI into business-relevant outcomes," with PPI offers behind it. Most teams will demo *an LLM that answers maintenance questions*. ForgeSight demos **a governed multi-agent decision-support system**: every answer cited to a manual/record/trend, every priority score deterministic and auditable, every agent operating under an explicit charter with budgets and human approval gates, every action timestamped in an audit trail — running on a physics-informed simulated steel plant with ML validated on NASA/UCI benchmarks — and **fully on-premise capable: the entire runtime executes on local hardware with a fine-tuned open-source SLM, so no plant data ever leaves the network and the live demo is internet-independent**. The pitch in one line: *"From fault code to fix plan in 90 seconds — auditable end to end, and it never phones home."*

---

# PART 1 — FULL-STACK SYSTEM ARCHITECTURE

## 1.1 Architecture at a glance

```
┌─────────────────────────── CLIENT (Next.js 15 · Vercel) ────────────────────────────┐
│ Plant Overview │ Priority Board │ Equipment Detail │ Reports & Logbook │ Admin       │
│                                                                        │ Console +   │
│ ── CopilotKit Sidebar (persistent): chat · SESSION HISTORY (timestamped,│ /simulate  │
│    resumable) · agent-delegation stream · AgentByline cards ·          (admin only)  │
│    Approve/Reject HITL prompts ──                                                    │
│ Supabase Auth (engineer|admin) · Realtime alert toasts · zod validation              │
└──────────────┬──────────────────────────┬───────────────────────────┬────────────────┘
               │ HTTPS+JWT                │ CoAgents (threadId=session)│ Realtime WS
               ▼                          ▼                            │
┌────────────────────── BACKEND (FastAPI, JWT-verified on every route) ┐│
│ ╔══════════════ GOVERNED MULTI-AGENT GRAPH (LangGraph) ════════════╗ ││
│ ║ AgentController: ingest_and_authorize → cache_lookup →           ║ ││
│ ║   classify_intent → Send FAN-OUT →                               ║ ││
│ ║   [Diagnostic│Reliability│Supervisor│Planner agents              ║ ││
│ ║    (deterministic charter PIPELINES, scoped tools — no free      ║ ││
│ ║     ReAct loops; SLM only at synthesis/repair, constrained)]     ║ ││
│ ║   → synthesize → guardrail_validate → {respond│human_gate│       ║ ││
│ ║                                        repair→guard│degrade}     ║ ││
│ ║ AgentAuthority: charters · action classes · role overlay ·       ║ ││
│ ║   budgets · escalation (COMMIT⇒HITL) · audited allow/deny        ║ ││
│ ║ AgentGuardrails: input guards · citation-existence gate ·        ║ ││
│ ║   LOTO-first · matrix-provenance · retry-once-then-degrade       ║ ││
│ ║ ForgeState: reducer channels (delegations·citations·budget)      ║ ││
│ ╚═══════════════════════════════════════════════════════════════════╝ ││
│ Tools: RAG(pgvector) · ML(joblib: IForest/XGB/LightGBM+SHAP) ·        ││
│   deterministic priority matrix & procurement rule · ReportLab PDF    ││
│ Per turn: LangGraph checkpoint (thread_id=session_id) + chat_messages ││
│ Caching chain: demo→semantic(pgvector)→TTL→prompt-prefix→KV(⭐LMCache)││
│ APScheduler 30s health scan → alerts · Langfuse tracing on everything ││
└──────┬───────────────┬──────────────────────────────┬─────────────────┘│
       ▼               ▼                              ▼                  │
┌──────────────┐ ┌────────────────────┐ ┌──────────────────────────────┐ │
│ SLM RUNTIME  │ │ Hosted LLM         │ │ SUPABASE (cloud free tier)   │◄┘
│ Ollama Qwen  │ │ (DEV-TIME: SFT data│ │ Postgres+pgvector · Auth+RLS │
│ 2.5-3B/7B FT │ │ gen + DeepEval     │ │ Realtime · chat_sessions/    │
│ Q4, format-  │ │ judge · RUNTIME:   │ │ messages · checkpoints+store │
│ constrained  │ │ hybrid fallback    │ │ audit_log                    │
│ ⭐vLLM+LMCache│ │ flag only)         │ │                              │
└──────────────┘ └────────────────────┘ └──────────────────────────────┘
Offline: Colab T4 — Unsloth fine-tune · ML training (C-MAPSS/AI4I/CWRU/Steel Plates)
→ versioned /models + metrics.json · DeepEval golden-set CI · Langfuse Cloud
```

## 1.2 Technology stack (consolidated)

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 · Tailwind · shadcn/ui · Recharts · lucide-react · CopilotKit CoAgents |
| Auth | Supabase Auth (JWT, 2 roles) · Next.js middleware · FastAPI JWT dependency · Postgres RLS |
| Agent runtime | LangGraph StateGraph (custom controller) — sub-agents as deterministic charter pipelines (fixed tool sequences per intent; no free-form ReAct loops) · Postgres checkpointer + store |
| Governance | AgentAuthority (charters/budgets/escalation) · AgentGuardrails (code-level) · governed_tool wrapper (InjectedState) |
| LLMs | **SLM-first runtime (`MODEL_BACKEND=slm_only`, default):** fine-tuned Qwen2.5-3B-Instruct (7B if VRAM rehearsal allows) via Unsloth→Ollama Q4 carries ALL runtime LLM calls — classify_intent, every card synthesis, repair, report prose — with Ollama `format=<schema>` **constrained decoding** so schema-invalid JSON is structurally impossible. Hosted models (Claude/Groq) are dev-time only (SFT data generation, DeepEval judge) + a tested `hybrid` fallback flag. SLM long-context rule: summarize histories >8 turns |
| Embeddings | nomic-embed-text (Ollama) |
| ML | IsolationForest (anomaly) · XGBoost (AI4I failure clf · C-MAPSS RUL) · LightGBM leakage-safe pipeline + SHAP (steel defect) · deterministic priority matrix & procurement/severity rules |
| Data & retrieval | Supabase Postgres + pgvector (HNSW + GIN) · 3 retrieval modes: hybrid metadata-filtered RAG · match_history · governed text-to-SQL over read-only views · materialized hourly aggregates |
| Caching | demo_cache → semantic_cache (knowledge-class only, ≥0.95) → cachetools TTL → static-first prompt prefix → ⭐ vLLM+LMCache (Colab T4 + cloudflared) → embedding hash-dedupe |
| Obs/Eval | Langfuse Cloud (node spans, sessions, feedback scores) · DeepEval golden set (faithfulness, contextual P/R, LOTO GEval, JSON validity; base-vs-FT table) |
| Reports | ReportLab PDFs |
| Deploy | Frontend → Vercel · stateful backend (graph/scheduler/ML/Ollama) → always-on container (Railway/Render) or the RTX 3060 laptop + cloudflared tunnel · Supabase cloud (see §1.12 — Vercel Functions are stateless and can't host the scheduler/SLM/warm models) |

## 1.3 Role model: 2 humans + 4 chartered agents

| Actor | Type | Authority (summary of charter) |
|---|---|---|
| **Engineer** ("Arjun", primary login) | Human | READ/WRITE/REPORT/COMMIT: dashboard, chat + own session history, feedback, logbook, alert ack, reports, approve agent proposals |
| **Admin** (judging login) | Human | Engineer capabilities + SIMULATE (/simulate) + Admin Console (audit log, metrics, all-sessions read-only) |
| **Diagnostic Agent** | AI | READ · pipeline: retrieve_rag → match_history → SLM synthesis · scopes: doc_chunks, breakdown_history · tool budget 6 |
| **Reliability Agent** | AI | READ · pipeline: check_equipment_health → estimate_rul (→ analyze_defect) · scopes: sensor_readings, equipment_health |
| **Supervisor Agent** | AI | READ+REPORT · pipeline: score_priority (deterministic) → narration · draft_shift_summary · narrates the matrix, never computes |
| **Planner Agent** | AI | READ+COMMIT · pipeline: check_spares → procurement_rule (→ propose_reservation) · COMMIT ⇒ mandatory human_gate |

Governance invariants (structural, not prompted): a tool absent from a charter cannot be bound *and* is re-checked at runtime (two layers must both fail); no agent is chartered for SIMULATE — fault injection is unreachable from chat; role overlay intersects human role with agent action on every call; every allow/deny decision is written to audit_log + Langfuse.

**Why pipelines instead of ReAct loops (the SLM-first enabler):** each agent's tool sequence is fully determined by intent — there is no genuine dynamic tool selection in this domain. Replacing "LLM decides the next tool" with "the charter defines the pipeline" removes the one capability that demanded a large hosted model (reliable multi-round free-form tool-calling), makes agent behavior deterministic and demo-reliable, and is *more* governed, not less. The SLM is invoked only at synthesis and repair, under constrained decoding, with the guardrail catching semantic violations (fabricated citations, safety ordering, matrix provenance). Charter, delegation events, AgentBylines, and the parallel Send fan-out are all unchanged. Backend is a config switch (`MODEL_BACKEND = slm_only | hybrid`); demo mode is decided at the end of Phase 2 by inspecting real Scenario-A cards, with `slm_only` as the default and the on-prem story as the prize.

## 1.4 The governed agent graph — state, nodes, edges

**ForgeState channels (reducer-backed, parallel-safe):** `messages` · identity set-once (`user, session_id, equipment_id`) · routing (`intent, query_class, target_agents`) · accumulated via reducers (`delegations[] → activity stream`, `citations[] → evidence chips`, `tool_results{}`, `consumed: Budget` additive across branches) · synthesis (`draft_card, guard_report, repair_attempted, pending_action, cache_hit`).

**Node inventory**

| Node | Kind | Responsibility |
|---|---|---|
| ingest_and_authorize | code | input guards (auth presence, equipment-ID existence, injection markers → data-only downgrade, length cap) |
| cache_lookup | code | demo_cache → semantic_cache chain (knowledge-class only) |
| classify_intent | SLM (constrained decode over the intent enum) | intent + query_class + target_agents from INTENT_AGENT_MAP |
| diagnostic / reliability / supervisor / planner agents | charter pipelines (code-ordered tool sequences) | charter-scoped tools via governed_tool wrapper; SLM never selects tools |
| synthesize | SLM (format-constrained) | merge tool_results + citations into ONE structured card; all numbers copied from tool_results |
| guardrail_validate | code | schema validity · **citation-existence gate** (every ref must exist in state) · LOTO-first ordering · enum/numeric sanity · **matrix-provenance** (priority score must originate from score_priority) |
| repair | SLM (format-constrained) | retry-once with the violation list as feedback |
| degrade | code | honest fallback card: raw retrieval + tool outputs, labelled |
| human_gate | interrupt | COMMIT-class proposals pause the checkpointed graph; Approve/Reject rendered in chat; resume carries decision; only then persisted |
| serve_cached | code | cached card + served_from_cache flag |
| respond | code | single egress: chat_messages insert (agent_name + timestamps), session updated_at bump, semantic-cache write, Langfuse mirror |

**Edge inventory**

| From → To | Type | Condition |
|---|---|---|
| START → ingest_and_authorize | unconditional | — |
| ingest_and_authorize → cache_lookup | unconditional | — |
| cache_lookup → serve_cached / classify_intent | **conditional** | cache hit / miss |
| classify_intent → sub-agents | **conditional (Send fan-out)** | one Send per target agent — parallel for multi-faceted intents (e.g. wait_assessment → Reliability + Planner + Supervisor) |
| each sub-agent → synthesize | unconditional | join point |
| synthesize → guardrail_validate | unconditional | — |
| guardrail_validate → respond / human_gate / repair / degrade | **conditional (4-way)** | pass / pass+pending_action / fail first time / fail after retry |
| repair → guardrail_validate | unconditional | retry loops back THROUGH the guard, never around it |
| degrade · human_gate · serve_cached → respond | unconditional | — |
| respond → END | unconditional | — |

Safety nets: outer `invoke` catches GraphRecursionError → degraded card (never a 500 on stage); AuthorityError → "Action not permitted" card + audit entry. The full implementation lives in `agent_governance.py` (deliverable file already drafted).

## 1.5 Database schema (Supabase)

```
profiles(id=auth.users.id, full_name, role enum('engineer','admin'), area)
equipment(id, name, zone, criticality 1-10, photo_url, thresholds jsonb)
sensor_readings(id, equipment_id, ts, vibration_de/nde, bearing_temp, motor_current, rpm, load_pct)
sensor_hourly_agg  -- MATERIALIZED VIEW
equipment_health(equipment_id PK, computed_at, anomaly_score, is_anomalous, rul_days,
                 rul_band jsonb, contributing_sensors jsonb)      -- inference cache + dashboard
alerts(id, equipment_id, severity enum(info,warning,high,critical), title, detail jsonb,
       target_role, created_at, acked_by, acked_at)
breakdown_history(id, equipment_id, occurred_at, fault_code, symptoms, root_cause,
                  resolution, downtime_hrs, verified bool)
spares(part_no, equipment_id, description, stock_qty, lead_time_days, supplier)
doc_chunks(id, equipment_id, doc_type enum(manual,sop,report), section_ref, content,
           content_hash, embedding vector(768))                   -- HNSW
semantic_cache(id, equipment_id, query_text, query_embedding, response_json,
               query_class enum(knowledge,live_status,action), expires_at)
chat_sessions(id PK = LangGraph thread_id, user_id, title, equipment_id?, created_at,
              updated_at, is_archived)
chat_messages(id, session_id cascade, role enum(user,assistant,agent_event), content,
              card_json jsonb, agent_name, created_at)
feedback(id, user_id, session_id, message_id, verdict enum(up,down,fixed), note,
         equipment_id, created_at)
logbook(id, equipment_id, author_type enum(system,human), author_id, entry_type,
        content jsonb, created_at)
reports(id, type, equipment_id?, generated_by, pdf_path, summary, created_at)
audit_log(id, user_id?, agent_name?, action, resource, allowed bool, reason?, detail jsonb, ts)
rejected_readings(raw jsonb, reason, ts)
pending_actions(id, session_id, proposal jsonb, status enum(pending,approved,rejected),
                decided_by, decided_at)                            -- HITL persistence
-- Phase-3 analytics: read-only VIEWS exposed to a SELECT-only Postgres role only
v_breakdown_stats · v_spares_status · v_alert_feed · v_downtime_by_equipment
-- (curated, no sensitive columns; text-to-SQL can reach ONLY these)
-- LangGraph-owned: checkpoints, checkpoint_writes, store
```
Dual chat persistence by design: checkpoints = agent memory (reasoning resumption); chat_messages = UI memory (list/render/timestamp without deserializing); same id ⇒ identity can never diverge. RLS on everything: sessions/messages scoped to `auth.uid()` (admin read-all); audit_log insert-only via service role; anon key only in the browser.

## 1.6 Proactive pipeline (FR-5, FR-7)

`/simulate (admin)` replayer → sensor_readings inserts (1×/10×/60×) → APScheduler 30 s per equipment: cached feature build → IsolationForest → if anomalous → RUL → UPSERT equipment_health → state-worsened ⇒ INSERT alert under deterministic severity rules (warning = score>0.6 sustained 3 windows · high = projected threshold crossing <14 d · critical = limit breached now OR rul_days < spares lead_time) → Supabase Realtime → role-filtered toast → auto logbook entry → one-tap Abnormal Alert Report.

## 1.7 Knowledge base & RAG (§4.3 · FR-2)

**Corpus (seeded once in Phase 0 by `seed_corpus.py`):** a blend of 2–3 real OEM manuals for authenticity (ABB ACS880 / Siemens SINAMICS VFD → F3 stand; SKF bearing handbook + centrifugal-fan O&M → sinter fans), ~10 synthetic steel-specific SOPs (authored LOTO-first so the ChecklistCard guardrail is satisfied straight from the corpus), and ~120 synthetic breakdown records. Firecrawl is used **dev-time only** to scrape HTML-only OEM knowledge/fault-code pages → markdown; it is never in the runtime path (preserves the on-prem story). Spares are **deliberately not embedded** — availability and lead time are volatile structured data served by the Planner's `check_spares` SQL tool; that is the §4.3 spares coverage, and keeping volatile data out of the vector store is the defensible choice.

**Chunking — structure is the signal, one strategy per type:**
- **Manuals (PDF, PyMuPDF):** section-aware two-stage split (split on numbered headings, then recursive ~800-char within section), with the section header **prepended into every chunk** for context anchoring; **fault-code tables are exploded into one atomic chunk per code** (`Fault F0247: DC bus overvoltage…`) so exact-code lookup never breaks mid-row.
- **SOPs (markdown):** `MarkdownHeaderTextSplitter` — **one complete procedure per chunk**, never splitting a step list (a truncated procedure missing its LOTO steps is the worst failure mode; the guardrail would reject and degrade on camera).
- **Breakdown records:** **no split** — one labelled block per record (FAULT|SYMPTOMS|ROOT CAUSE|RESOLUTION|DOWNTIME); `verified` flag rides in `section_ref` → green chip.

**Store:** plain SQL on the custom `doc_chunks` schema (LangChain used for loaders+splitters only — its `PGVector` class is skipped because it would fight RLS and the `content_hash` dedupe). Embeddings via Ollama `nomic-embed-text`; HNSW index for vectors + GIN index for full-text. Re-ingestion is free (content_hash `ON CONFLICT DO NOTHING`).

**Retrieve (`rag_retrieval.py`, runtime):** **hybrid + metadata-filtered** — `equipment_id` filter applied before similarity search (a sinter-fan query can never retrieve the caster's manual — sharper results *and* a clean explainability claim), then RRF-style fusion of vector cosine (0.7) and full-text `ts_rank` (0.3). The full-text leg is essential here because **fault codes and part numbers (`F0247`, `SKF 22230`) are exact-match tokens embeddings handle poorly.** Retrieved chunks are sorted by id before prompt assembly so identical retrievals yield identical prefixes (keeps prefix/KV caching effective). Each chunk's `id`/`section_ref` becomes a `Citation` in ForgeState → validated by the citation-existence guardrail → shown in the Evidence Drawer and the Docs tab. `match_history` reuses the same retriever scoped to `report` chunks with verified records floated to the top. Skipped for scope: cross-encoder rerank, parent-document retrieval (hybrid + metadata filtering reaches ~90% quality at ~200–300 chunks).



## 1.8 Caching · observability · evaluation

Lookup chain: `demo_cache (exact, scripted) → semantic_cache (≥0.95, knowledge-class ONLY — live-status is never cached: stale RUL is dangerous) → TTL (sensor 30 s · dashboard 15 s · spares 5 m) → prompt prefix (static-first ordering; Claude cache_control) → KV (⭐ vLLM+LMCache on Colab T4 via cloudflared; Ollama otherwise) → DB (materialized view · content_hash embedding dedupe · equipment_health as persistent inference cache)`. Invalidation: new alert/feedback purges that equipment's semantic rows; doc re-ingest purges knowledge rows; model version bump recomputes health.

Langfuse Cloud: CallbackHandler everywhere; session_id = chat session; sub-agent delegations as nested spans (the multi-agent trace tree is a submission screenshot); chunk IDs in span metadata = the same IDs as UI evidence chips; UI feedback mirrored as scores. DeepEval: 25–40 golden cases; Faithfulness · Answer Relevancy · Contextual P/R · GEval "LOTO-first" · JSON-validity assertion; hosted judge (never the 3B); base-vs-fine-tuned Qwen table (FR-1 merit evidence); rerun as the regression gate before the final zip.

## 1.7b Analytical retrieval — governed text-to-SQL (§4.1/§4.3 · FR-2, Phase-3 enhancement)

Three retrieval modes, each used where it is strongest: **deterministic tools** for the operational hot path (priority matrix, severity rules, `check_spares`), **RAG** for documents, and **governed text-to-SQL** for open-ended *analytical* questions over records/logs that no fixed tool can pre-cover — "how many F3 trips this year and the most common root cause?", "which equipment had the most downtime last quarter?", "list unacked critical alerts in the sinter zone". This is the part of FR-2's "reason over records/logs" that vector RAG handles poorly: RAG retrieves documents, it does not count or aggregate.

Implemented as one governed tool (`query_records`) on an **Analyst capability** (added to the Supervisor Agent's charter, READ-only), with hard rails that preserve every system guarantee:
- **Read-only at the database, not the prompt:** a dedicated Postgres role with `GRANT SELECT` only, on a **whitelist of curated read-only views** (`v_breakdown_stats`, `v_spares_status`, `v_alert_feed`, `v_downtime_by_equipment`). Structurally incapable of writing — the same discipline as charter tool-binding. Raw tables, auth tables, `audit_log`, and `chat_*` are unreachable.
- **Small schema = higher SQL accuracy** (critical for the 3B SLM): views are tiny and well-named; LangChain `SQLDatabaseToolkit` is primed with few-shot question→SQL examples.
- **Visible SQL = explainability, not risk:** the generated query renders in an **SqlCard** (query + result table), and the SQL itself becomes `Citation(kind="sql_query", ref=<sql>)` — so the citation-existence and **number-fidelity** guardrails extend to it: the SLM narrating a result cannot state a count absent from the returned rows.
- **Validation:** `EXPLAIN` the query before executing; reject on error → retry once → degrade. New guardrail checks: `sql_is_select_only · query_targets_whitelisted_views · numbers_in_card_match_result_rows`.
- **Hybrid-fallback candidate:** text-to-SQL is the hardest generation task for a 3B model; if rehearsal shows unreliable SQL, route *only* this tool to a hosted model (analytical queries are infrequent — contained sovereignty cost) while everything else stays local.

Not used to replace any deterministic tool — those must be exactly right and auditable as code, never generated on the fly.



ForgeSight enforces trust at three independent tiers; any single failure is caught by another. This framing is itself a slide.

### Tier 1 — Human authentication & authorization (Supabase Auth)
- Two roles: `engineer`, `admin`. Role in `profiles`, injected into the JWT (access-token hook / app_metadata).
- **Seeded, pre-confirmed demo accounts** in the README (`engineer@demo.forgesight`, `admin@demo.forgesight`) so judges log in instantly; email verification ON for self-registration, OFF for seeds — stated explicitly as the prototype posture.
- Frontend: `@supabase/ssr` cookie sessions; middleware redirects unauthenticated users and blocks `/simulate` + `/admin` for non-admins (UI gating = convenience).
- Backend (the real gate): FastAPI `current_user` dependency decodes/verifies the Supabase JWT (HS256, audience `authenticated`) on EVERY route including the CopilotKit endpoint; `require_role("admin")` on `/simulate/*` and `/admin/*`. User id + role enter ForgeState — agents are role-aware; history queries always scoped `user_id = auth.uid()`.
- DB safety net: RLS mirrors the same rules; the service-role key never leaves the server.

### Tier 2 — Agent authority (governance — machine actors get the same rigor as humans)
- Per-agent **charters**: allowed tools, action classes (READ/WRITE/REPORT/COMMIT/SIMULATE), data scopes, recursion limit, per-turn tool budget.
- `governed_tool` wrapper checks charter + human-role overlay + budget BEFORE execution; `InjectedState` keeps identity/context out of the LLM-visible schema (unspoofable).
- **Escalation:** COMMIT-class actions (reserve spare, draft PO) can only be PROPOSED; the `human_gate` interrupt pauses the checkpointed graph until the engineer taps Approve/Reject in chat; the decision + decider + timestamp persist to `pending_actions` + `audit_log`. Nothing commits without a human — a runtime property, not a promise.
- Every authority decision — allow AND deny — is audited.

### Tier 3 — Validation & output verification
- **Frontend:** zod on all forms (UX only, never trusted).
- **API:** Pydantic v2, `extra='forbid'`, constrained types/enums/bounds on every body.
- **Agent inputs:** chat text is data, not tool instructions; tool args exist only as LLM-filled Pydantic schemas; tool layer re-validates equipment/part IDs against the DB (blocks injection-driven probing); injection markers downgrade text to data-only and ride to the audit log.
- **Agent outputs (guardrail_validate, code not LLM):** schema validity · citation-existence gate (a reference that wasn't actually retrieved physically cannot reach the user) · LOTO-first ordering · enum/numeric sanity · matrix-provenance. Retry-once-with-violations → degraded-honest fallback. GraphRecursionError → degraded card, never a 500.
- **Ingestion:** replayer rows range/timestamp-validated; bad rows quarantined to rejected_readings.
- **Human verification of AI output:** "✓ This fixed it" sets breakdown_history.verified=true; only verified records earn the green "Engineer-verified" chip — AI suggestions and confirmed facts are never visually conflated.
- **Model verification:** metrics.json per artifact (CV scores, leakage-safe per-fold pipeline, threshold provenance) → "About the models" panel; DeepEval report committed in-repo.
- **API hardening:** CORS allowlist, slowapi rate limit (20 chat req/min/user), request-size caps, HTTPS end-to-end.

## 1.10 ML model development (FR-5 · §5.1) — datasets, models, training, artifacts

All ML is **trained offline (Colab T4 free), served as versioned `joblib`/`json` artifacts loaded once at FastAPI startup, and exposed as governed tools** that return Pydantic models. Never trained in the request path. Methods are validated on real public run-to-failure benchmarks; the system is demonstrated on the physics-informed synthetic steel layer (the honest framing for the assumptions section: *benchmarks validate the method, the simulation validates the system*).

**Models & algorithms (deliberately explainable — a feature for plant-engineer judges):**

| Model | Algorithm | Trained on | Headline metric | Why this choice |
|---|---|---|---|---|
| Anomaly detection | IsolationForest + per-sensor rolling z-score / EWMA control limits | synthetic stream (healthy 20 d) | precision/recall + **detection lead time** ("flagged 6.2 d before threshold") | unsupervised — honest "no failure labels in a real plant"; control charts are what plants actually use |
| Failure classification | XGBoost (`scale_pos_weight`, stratified) | AI4I 2020 (10k×14) | **failure-class F1/recall** (never accuracy — 3.4% positive) | feature importances/SHAP → explainable diagnosis; drop RNF (unlearnable) and UDI/Product ID (leakage) |
| RUL regression | XGBoost/RandomForest on windowed features (Tier-1 trend extrapolation for the UI) | C-MAPSS FD001 | RMSE ~16–18 cycles | piecewise-linear RUL cap at 125; **split by engine unit, never by row** (row split leaks → fraudulent RMSE) |
| Bearing-fault features | RMS / kurtosis / crest-factor windows | CWRU 12 kHz drive-end | classifier acc. | feeds the sinter-fan narrative; degradation *shape* template from NASA IMS |
| Process-defect detection | LightGBM hybrid: PCA-reconstruction-residual + kNN-distance-to-normal as features + missingness flags | UCI Steel Plates Faults (steel-domain) | PR-AUC + recall@threshold | **leakage-safe per-fold fitting** (PCA/kNN/scaler refit inside each CV fold), OOF-only threshold (precision-first → F-beta=3 fallback), SHAP top contributors → evidence chip |

**Training discipline (state in docs — judges score rigor):** RepeatedStratifiedKFold; `StratifiedGroupKFold` if batch/heat structure exists; per-fold pipeline (no leakage); OOF threshold selection; PR-AUC headline for imbalanced tasks; `metrics.json` committed per artifact (CV scores, threshold provenance) → surfaced in the "About the models" panel and the DeepEval-style results table in the submission.

**Artifacts & serving:** `/models/{anomaly_iforest_v1.joblib, scaler_v1.joblib, failure_xgb_v1.json, rul_xgb_v1.joblib, defect_pipeline_v1.joblib, threshold.json, feature_config.json, metrics.json}`. `feature_config.json` (window sizes, column order, scaling) is read by **both** training and inference so feature computation is byte-identical (train/serve parity — the classic silent ML bug). Loaded once in the FastAPI lifespan into `app.state`; wrapped as governed tools (`check_equipment_health`, `estimate_rul`, `analyze_defect`) returning Pydantic results.

## 1.11 Pydantic as the system-wide contract

Pydantic v2 is the single schema layer binding the LLM, the tools, the API, and the frontend cards — one definition, four consumers, so drift is structurally impossible:
- **Structured agent outputs:** `Diagnosis`, `ChecklistCard`, `WaitAssessment`, `RiskAssessment`, `PriorityResult`, `SparesResult`, `DefectResult`, `RULEstimate`, `SqlCard` — these *are* the frontend card props (frozen schema-first in Phase 0) and the SLM's constrained-decode targets.
- **Tool I/O:** every governed tool returns a Pydantic model (`ToolOutcome.payload`); tool args are LLM-filled Pydantic schemas re-validated against the DB.
- **API boundary:** every FastAPI request/response model uses `model_config = ConfigDict(extra="forbid")`, constrained types (`constr`, `Field(ge=, le=)`), and enums.
- **ML results:** model outputs are Pydantic, so `rul_days ≥ 0` / `risk_level ∈ enum` are enforced before they reach a card and re-checked by the guardrail.
Docs: https://docs.pydantic.dev · constrained decoding to these schemas via Ollama `format` https://ollama.com/blog/structured-outputs

## 1.12 Deployment topology (the honest split)

A single "FastAPI on Vercel" deployment does **not** fit this app: Vercel Functions are stateless/serverless with a 500 MB bundle cap and ≤500 ms shutdown window, which is incompatible with APScheduler's persistent 30 s scan, Ollama serving the local SLM (no GPU, model exceeds the bundle), warm ML artifacts, and pooled LangGraph checkpoint connections. Reference (and its limitations section): https://vercel.com/docs/frameworks/backend/fastapi · https://vercel.com/docs/functions/limitations

**Recommended split:**

| Component | Host | Rationale |
|---|---|---|
| Next.js frontend | **Vercel** | Native target; CDN, edge, preview deploys · https://vercel.com/docs |
| Stateless API edge (optional) — auth callback, lightweight read endpoints, webhooks | **Vercel Functions (FastAPI)** | The doc's `app`-at-entrypoint pattern fits *stateless* routes only; `lifespan` for DB connect/cleanup · https://vercel.com/docs/frameworks/backend/fastapi |
| **Stateful backend** — LangGraph graph, governed tools, APScheduler, ML artifacts, RAG | **Railway / Render / Fly.io (always-on container)** | Persistent process, background scheduler, warm models · https://render.com/docs · https://docs.railway.app · https://fly.io/docs |
| **SLM serving** — Ollama Qwen Q4 (⭐ vLLM+LMCache) | **The RTX 3060 laptop (demo)** via cloudflared tunnel; or a GPU host for prod | On-prem story; no GPU on Vercel/Render free tiers · https://github.com/cloudflare/cloudflared |
| Postgres + pgvector + Auth + Realtime | **Supabase cloud** | Managed, free tier · https://supabase.com/docs |
| Offline training + fine-tune | **Colab T4** | Free GPU · https://colab.research.google.com |

For the hackathon demo specifically, the simplest reliable topology is: **frontend on Vercel, the full stateful backend + Ollama on the RTX 3060 laptop, exposed via a cloudflared tunnel, talking to Supabase cloud** — which also reinforces the on-prem/sovereignty narrative and removes any cloud-function cold-start or size-limit risk during live judging. Containerize the backend (Dockerfile) at the end for the submission ZIP so it's reproducible anywhere.

---

# PART 1.5 — REFERENCE LINKS (tools · datasets · frameworks · models)

**Frontend/agent UI:** Next.js https://nextjs.org/docs · CopilotKit https://github.com/CopilotKit/CopilotKit / https://docs.copilotkit.ai · shadcn/ui https://ui.shadcn.com · Tailwind https://tailwindcss.com/docs · Recharts https://recharts.org
**Backend/agents:** FastAPI https://fastapi.tiangolo.com · LangGraph https://github.com/langchain-ai/langgraph · checkpoint-postgres https://reference.langchain.com/python/langgraph.checkpoint.postgres · LangChain text-to-SQL (SQLDatabaseToolkit) https://python.langchain.com/docs/tutorials/sql_qa/ · APScheduler https://apscheduler.readthedocs.io · Pydantic https://docs.pydantic.dev · ReportLab https://www.reportlab.com/opensource/
**LLM/SLM:** Qwen2.5 https://huggingface.co/Qwen/Qwen2.5-3B-Instruct · Ollama https://ollama.com/library/qwen2.5:3b-instruct · structured outputs https://ollama.com/blog/structured-outputs · Unsloth https://github.com/unslothai/unsloth · TRL https://huggingface.co/docs/trl · embeddings nomic-embed-text https://ollama.com/library/nomic-embed-text · ⭐ vLLM https://docs.vllm.ai · ⭐ LMCache https://github.com/LMCache/LMCache · Claude API (dev-time) https://docs.claude.com · Groq https://console.groq.com/docs
**ML:** scikit-learn https://scikit-learn.org · XGBoost https://xgboost.readthedocs.io · LightGBM https://lightgbm.readthedocs.io · SHAP https://shap.readthedocs.io · ucimlrepo https://pypi.org/project/ucimlrepo/
**Data/DB:** Supabase https://supabase.com/docs · pgvector https://github.com/pgvector/pgvector · Firecrawl (dev-time corpus seeding) https://docs.firecrawl.dev
**Obs/Eval:** Langfuse https://langfuse.com/docs · LangGraph integration https://langfuse.com/integrations/frameworks/langgraph · DeepEval https://deepeval.com/docs/getting-started
**Deploy:** Vercel FastAPI https://vercel.com/docs/frameworks/backend/fastapi · Vercel Functions limits https://vercel.com/docs/functions/limitations · Render https://render.com/docs · Railway https://docs.railway.app · Fly.io https://fly.io/docs · cloudflared https://github.com/cloudflare/cloudflared

**Datasets (download early; commit a `fetch_data.py`):**
- NASA C-MAPSS FD001 (RUL) — repo https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/ · zip https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip · Kaggle https://www.kaggle.com/datasets/bishals098/nasa-turbofan-engine-degradation-simulation
- AI4I 2020 (failure classification) — UCI https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset · Kaggle https://www.kaggle.com/datasets/stephanmatzka/predictive-maintenance-dataset-ai4i-2020
- CWRU bearing (vibration) — official https://engineering.case.edu/bearingdatacenter · Kaggle https://www.kaggle.com/datasets/brjapon/cwru-bearing-datasets
- NASA IMS bearing (run-to-failure degradation shape) — PCoE page above · Kaggle https://www.kaggle.com/datasets/vinayak123tyagi/bearing-dataset
- UCI Steel Plates Faults (steel-domain defect classifier) — https://archive.ics.uci.edu/dataset/198/steel+plates+faults
- Microsoft Azure PdM (schema template / optional 2nd benchmark) — https://www.kaggle.com/datasets/arnabbiswas1/microsoft-azure-predictive-maintenance
- Synthetic steel layer — generated by `seed_corpus.py` + the sensor generator (degradation shapes borrowed from NASA IMS)

---

# PART 2 — SCENARIO-BASED UI/UX PIPELINE

## 2.1 Actors on screen
**Arjun (engineer login)** drives Scenarios A–C. **Admin (your login)** drives /simulate from a second window and closes the demo on the Admin Console. **The four agents appear inside the conversation** — named delegations in the activity stream, AgentByline chips on cards, and (new in v3) **Approve/Reject governance prompts** when the Planner proposes a commitment.

## 2.2 Information architecture
```
/login → role-aware landing
1 Plant Overview — zone-map grid (plant-flow layout) · KPI strip (availability, open
  alerts, ₹ downtime-at-risk) · live alert feed
2 Priority Board — ranked issues · score-breakdown drawer ("Deterministic scoring ·
  auditable") · what-if controls
3 Equipment Detail /equipment/:id — health header (status·risk·RUL countdown) · trend
  charts (normal band, threshold lines, molten-orange anomaly markers) · tabs:
  History | Spares | Docs | Past Conversations
4 Reports & Logbook — report list + PDF preview · per-equipment timeline (system grey
  rail / human blue rail)
5 Admin Console (admin) — audit log (incl. agent allow/deny decisions) · model metrics ·
  all-sessions read-only
6 /simulate (admin) — inject degradation · trip fault · replay 1×/10×/60× · reset
Persistent: CopilotKit sidebar — chat · session history · delegation stream · cards ·
  HITL approval prompts
```

## 2.3 Design system — "control room, not SaaS"
Dark graphite `#0E1116`/panels `#161B22` (pulpit-correct default); steel-blue `#4A90D9` primary; **molten-orange `#FF6A2B` reserved exclusively for live/critical**; status `#3FB68B/#E8B931/#E5484D`. Mono (JetBrains/IBM Plex) for ALL telemetry, IDs, fault codes, RUL, timestamps; Inter for UI. **Signature: the Evidence Trail** — chips under every AI claim (`📄 SOP-HSM-114 §3.2 · 📈 14d trend · 🕓 BR-2023-0847 · ⚙ priority matrix`) opening an Evidence Drawer with the exact excerpt/chart/record. Atoms built first: StatusBadge, RiskPill, RulCountdown, EvidenceChip, SparesChip, AgentByline, SessionRow, **ApprovalPrompt** (v3).

## 2.4 Copilot sidebar — chat, history, delegation, governance
- Header: current session title · 🕓 history · ＋ New chat.
- **Session history:** grouped Today/Yesterday/Earlier; SessionRow = auto-title ("F3 VFD overvoltage trip") + equipment chip + relative timestamp (exact on hover), sorted by updated_at. Tap → chat_messages render (cards from card_json), CopilotKit threadId = session id → checkpoint restores full reasoning context. Resume works across logins and restarts.
- **In-chat timestamps:** mono stamp per message group; date dividers on resumed multi-day sessions — same treatment as logbook/audit.
- **Delegation stream:** live rows while the graph runs ("→ Planner Agent: checking SKF 22230 lead time…"), collapsing to "View reasoning"; AgentByline on each card.
- **ApprovalPrompt (v3):** when the graph hits human_gate, the stream pauses and an amber card renders the proposal ("Reserve SKF 22230 — 1 unit from stock for Fan #2?") with Approve / Reject. The decision resumes the graph and lands in the audit log with the decider + timestamp.
- **SqlCard (Phase-3 analytics):** for free-form analytical questions, renders the generated SQL query + result table + a one-line narration; the SQL is the citation. Visible-query-as-explainability, consistent with the Evidence Trail.
- Scope guard: history list + resume + timestamps is complete — no in-history search, no message editing.

## 2.5 Scenario A — Reactive: fault code → cited fix plan
*PS §4.1, §4.4, §5.1 diagnosis/RCA, §5.3, FR-1/2/3/4/6.*
1. 06:40 — Arjun logs in. Plant Overview: F3 stand tile pulsing critical — "TRIPPED · HSM-F3-VFD-0247 · 12 min downtime." Most urgent thing findable in <2 s.
2. Click → Equipment Detail F3. Copilot auto-greets with route context: "F3 tripped 12 min ago on 0247 — want a diagnosis?" New session auto-created, auto-titled, equipment-tagged.
3. Diagnose → delegation stream: *Orchestrator → Diagnostic Agent: reading fault code… searching manuals… matching past breakdowns…*
4. **DiagnosisCard** (byline: Diagnostic Agent · `AI-assisted`): probable fault (DC bus overvoltage · confidence **High** in words), ranked root causes ①②③, evidence chips under each (① = BR-2024-0312, same stand, 14 mo ago). Open one chip on camera → Evidence Drawer shows the exact record.
5. Follow-up: "how do I check the braking resistor?" → **ChecklistCard** from SOP-HSM-ELEC-09 — LOTO steps first (amber, non-collapsible — the guardrail enforces this ordering), expected resistance values, checkable steps. Multi-turn pronoun resolution shown.
6. "✓ This fixed it" + one-line note → toast "Saved to F3 logbook · will inform future diagnoses."
7. **Resume beat:** close the browser entirely, log back in, reopen "F3 VFD overvoltage trip" from history — timestamps and cards intact — ask "did we ever check the deceleration ramp?" Correct answer from restored context. Persistent multi-turn memory, on camera, 20 seconds.
8. **Learning epilogue:** a similar F5 fault later → DiagnosisCard carries the green "✓ Engineer-verified fix · F3 · 11-Jun-2026" chip.

## 2.6 Scenario B — Proactive + governed: catch it early, commit with approval
*PS §4.2, §5.1 RUL/early warning, §5.2, §5.3 spares strategy, FR-5/7 + governance.*
1. Admin (second window) injects accelerating bearing degradation on Sinter ID Fan #2 via /simulate. Arjun's screen: amber toast — "⚠ Early warning — DE bearing vibration trending abnormal (score 0.81) · Est. RUL 9 days." Fan tile green→amber. **The system speaks first.**
2. Click-through → the showpiece chart: 30 d normal band, drift, molten-orange anomaly markers, labeled threshold line. The viewer sees why before reading a word.
3. **RUL panel:** large mono "≈ 9 days" · band 7–13 d · extrapolation sparkline · "At current trend, vibration crosses 7.1 mm/s around 20 Jun."
4. **"Can this wait until Sunday's shutdown?"** → delegation stream shows the parallel Send fan-out: *Reliability Agent: projecting RUL… · Planner Agent: SKF 22230 — 1 in stock, lead 21 d… · Supervisor Agent: scoring urgency…* → one synthesized card: **"Yes, with conditions"** — margin math (4 d to shutdown vs 9 d RUL), interim monitoring plan (sampling↑, alert at 6.5 mm/s), Planner callout "Lead time (21 d) > RUL (9 d): reserve the in-stock unit now."
5. **Governance beat (v3, the differentiator):** Arjun: "go ahead and reserve it" → Planner proposes → graph pauses at **human_gate** → ApprovalPrompt: "Reserve SKF 22230 — 1 unit for Sinter ID Fan #2?" → Arjun taps **Approve** → confirmation + audit entry. Say the line out loud: *"Agents propose; humans commit; everything is audited."*
6. One tap → Abnormal Alert Report (PDF) + auto logbook entry.

## 2.7 Scenario C — Prioritize, prove, report
*PS §5.2 prioritization & bottleneck, §5.4 reports/summaries/logbook.*
1. Arjun: "what should we tackle first tonight — one crew available?" → Supervisor Agent calls the deterministic matrix → **PriorityCard** (byline: Supervisor Agent · `rule-based score`) ranking 6 issues + "View on Priority Board."
2. Priority Board: ranked rows — equipment · issue · risk pill · score (mono) · four mini-bars (criticality · delay severity · spares · lead time). Score drawer: raw values × weights + plain sentence ("#1 because the caster is a plant bottleneck and the spare is in stock") + footer **"Deterministic scoring · auditable."**
3. What-if (zod+Pydantic validated): crew 1→2 · spare unavailable → animated re-rank in 300 ms.
4. **Analytics beat (Phase-3 enhancement):** Arjun asks a free-form question no fixed tool covers — "how many F3 overvoltage trips this year, and what was the most common root cause?" → Analyst capability generates SQL against `v_breakdown_stats` → **SqlCard** shows the query + result table + narration ("4 trips; most common root cause: braking-resistor degradation"). The visible SQL is the citation — "reasoning over logs," made auditable. (Demo only if the SLM's SQL is reliable in rehearsal; otherwise this tool runs on the hybrid fallback.)
5. "Generate shift maintenance summary" → progress states → preview (exec summary · per-issue diagnosis/actions/spares · evidence appendix) → Download PDF · Save to logbook.
6. Logbook: system (grey rail) vs human (blue rail) entries; Arjun's verified fix and his approval decision both visible.
7. **Closing beat — Admin Console:** audit log shows the morning — logins, the alert, the approval (who/when), even a denied-action row if you stage one ("Planner attempted out-of-charter tool — denied"). Model-metrics panel (CV scores, DeepEval results, cache TTFT). "Who did what, when" answered on screen.

## 2.8 Cross-cutting trust patterns
Evidence chips + drawer on every claim · confidence in words with basis tooltip · `rule-based` vs `AI-assisted` + AgentByline labels · LOTO-first non-collapsible safety steps (guardrail-enforced) · agents propose / humans commit (HITL) · graceful AI failure ("Couldn't complete the diagnosis — here are the matched SOP sections") with DEMO_MODE fallback armed · mono units/IDs/timestamps everywhere · loading/empty/error states specified for every screen.

## 2.9 Build pipeline (phased)
- **Phase 0 (½ d):** scenario scripts as literal demo dialogue · lo-fi wireframes (6 screens) · tokens into Tailwind · Pydantic/TS card schemas frozen schema-first · Supabase: tables + RLS + 2 seeded accounts · synthetic data generator + corpus · **SFT dataset generation kicked off (core path — see `sft-dataset-spec.md`: ~2,150 pairs across all 10 runtime tasks, generated by hosted model against the real tools, shared `prompt_builder.py` for train/serve parity)**.
- **Phase 1 (d1):** Next.js shell + auth middleware + login · **CopilotKit↔LangGraph hello-world with threadId persistence — verify a resumed thread restores context before building anything else** (highest-risk integration) · /simulate + replayer → Realtime toast pipeline · the 8 atoms · **Unsloth fine-tune trains on Colab T4 in parallel; automated quality gates + 50-sample manual review on the dataset**.
- **Phase 2 (d2 am):** Scenario A vertical slice on the governed graph (Diagnostic pipeline only first): governed_tool wrapper, guardrail_validate, DiagnosisCard/ChecklistCard/Evidence Drawer, session list + resume — running on the fine-tuned SLM with constrained decoding. Don't start B until A demos clean including the close-browser-resume beat. **End of Phase 2: the MODEL_BACKEND decision — inspect real Scenario-A cards; ship `slm_only` (default, on-prem story) or flip to `hybrid` fallback. Promotion rule: fine-tune ships only if it beats base Qwen on citation compliance AND number fidelity.**
- **Phase 3 (d2 pm–d3 am):** Reliability/Supervisor/Planner pipelines + Send fan-out + human_gate/ApprovalPrompt · Scenario B (anomaly markers, RUL panel, alerts, approval beat) · Scenario C (Priority Board, what-if, report+PDF, logbook) · Admin Console · Langfuse wired · **(if time) governed text-to-SQL analytics: read-only views + SELECT-only role + query_records tool + SqlCard + SQL guardrails**.
- **Phase 4 (final ½ d):** feedback round-trip + verified-chip epilogue · staged denied-action audit row · edge states · DEMO_MODE caches · DeepEval regression run committed · rehearse + record (Scenario B toast + approval beat in one unbroken take).
- **Team split (4):** frontend · agents/governance · ML+data · floater (auth, reports, integration, docs, video).

## 2.10 Five-and-a-half-minute demo choreography
0:00 problem framing on a green dashboard ("fragmented manuals, logs, tribal knowledge") → 0:30–2:10 **Scenario A** incl. evidence-chip open + close-browser-resume → 2:10–3:50 **Scenario B**: live toast ("the system speaks first") → three-agent fan-out on "can it wait?" → **Approve beat** ("agents propose; humans commit; everything is audited") → 3:50–4:40 **Scenario C**: what-if re-rank + PDF + logbook → 4:40–5:30 **Admin Console** (audit incl. agent decisions) + feedback epilogue + architecture slide + business numbers (downtime-hours-saved model, ₹0 per-token inference cost) + metrics table (ML CV · DeepEval base-vs-FT · cache TTFT) + the closing line: *"Everything you just saw ran on one laptop with an open-source fine-tuned model — fully on-premise capable, no plant data ever leaves the network."* 1080p, cursor highlight, /simulate on second window, cached fallback armed (the SLM-only runtime also means no API or internet dependency can kill the live session).

---

# PART 3 — FULL PS REQUIREMENT TRACEABILITY (v3)

| PS ref | Requirement | Satisfied by |
|---|---|---|
| §4.1 | Delay logs · fault/error messages · failure reports · incident records | breakdown_history + alerts ingestion · fault-code entry (Scenario A) · corpus in doc_chunks |
| §4.2 | Sensor summaries · anomaly alerts · process condition indicators | sensor_readings + replayer · IsolationForest alerts · equipment.thresholds |
| §4.3 | Manuals · SOPs · historical records · spares availability + lead time | doc_chunks RAG (manual/sop/report) · spares table · Planner Agent tools |
| §4.4 | NL queries · scenario prompts · multi-turn follow-ups | CopilotKit chat · checkpointed threads · timestamped session history with full resume |
| §5.1 | Diagnosis · RCA · RUL · catastrophic early warning · process-defect detection | DiagnosisCard ranked causes (Diagnostic Agent + fine-tuned Qwen) · cited RCA · RUL panel (Reliability Agent: trend + XGB on C-MAPSS) · critical severity rule (limit breach OR RUL<lead time) · LightGBM leakage-safe defect pipeline + SHAP (§1.10, validated on UCI Steel Plates / AI4I / CWRU) |
| §5.2 | Risk classes · urgency · plant bottleneck · prioritization by criticality/delay/spares/lead time | RiskPill enum + severity rules · Supervisor Agent urgency · Priority Board ranking · four scored components as mini-bars + auditable drawer (deterministic, guardrail-enforced provenance) |
| §5.3 | Step-by-step recs · immediate actions · optimized plan · long-term monitoring · spare procurement strategy | ChecklistCard (LOTO-first, enforced) · immediate-action block · "yes-with-conditions" plan · interim-monitoring recommendation · Planner lead-time-vs-RUL callout + governed reservation (human-approved) |
| §5.4 | Structured reports · abnormal alert reports · decision summaries · digital log entries | ReportLab PDFs · one-tap alert report (B) · shift summary (C) · logbook auto+human entries |
| §6 FR-1 | LLM/SLM contextual reasoning; merit for domain fine-tune; "publicly available APIs **may** be used" | **SLM-first runtime: the Unsloth fine-tuned Qwen2.5-3B/7B carries ALL runtime reasoning** (intent, synthesis, repair, reports) under constrained decoding — directly maximizing the fine-tune merit criterion and exercising the SLM option the PS explicitly sanctions; hosted APIs used only dev-time (SFT generation, DeepEval judge) + tested hybrid fallback · DeepEval base-vs-FT table + `sft-dataset-spec.md` as merit evidence · fully on-premise deployable |
| §6 FR-2 | Integrate & reason over manuals/SOPs/records/logs | **Three retrieval modes:** metadata-filtered hybrid pgvector RAG (manuals/SOPs) + match_history (verified-first) + **governed text-to-SQL over read-only views** for aggregate/analytical questions logs (count/aggregate, which RAG can't) · structure-aware chunking · Docs tab proves the corpus |
| §6 FR-3 | Context-aware multi-turn NL | Sidebar + thread checkpoints + route-derived equipment context + session resume across logins (demonstrated on camera) |
| §6 FR-4 | Explainable, traceable recommendations | Evidence chips/drawer · **citation-existence guardrail** (fabricated refs cannot reach the user) · matrix-provenance guard · rule-based vs AI-assisted + AgentByline labels · SHAP contributors · Langfuse trace tree |
| §6 FR-5 | Dynamic abnormality detection · early warning · failure prediction | APScheduler 30s scan · IsolationForest + control limits · deterministic severity rules · RUL pipeline — full model development, datasets, and training discipline in §1.10 |
| §6 FR-6 | Feedback-driven improvement | 👍/👎/✓-fixed → feedback table + LangGraph store + Langfuse scores + verified-record re-embedding → green-chip epilogue on camera |
| §6 FR-7 | Real-time alert reports · user-specific notifications | Realtime role-filtered toasts · one-tap alert report · target_role alerts |
| §7 opt | Conversational UI · dashboard · simulated IoT · dynamic per-equipment KB · auto logbook · role-based alerts/recs | Copilot · Plant Overview · /simulate replayer · doc_chunks + verified additions per equipment · auto logbook · 2-role model + role-aware, charter-governed agents |
| §8 | Downtime↓ · response time↓ · accuracy↑ · reactive→proactive · planning/spares · steel-plant applicability | Demo narrative + ₹-at-risk KPI + metrics tables (ML CV · DeepEval · cache TTFT) + steel equipment domain throughout |
| §9 | Source code · architecture/stack/dataflow/model/alerting docs · install guide · sample I/O · screen recording · single ZIP | Repo (incl. agent_governance.py) + this document + README (demo credentials, install) + golden-set sample I/O + OBS recording → one ZIP |
| (added) | Authentication · validation · verification | §1.8 three-tier trust model: human auth (JWT+RLS) · agent authority (charters, budgets, HITL escalation, audited allow/deny) · guardrails (citation-existence, LOTO-first, matrix-provenance, retry-then-degrade) |
