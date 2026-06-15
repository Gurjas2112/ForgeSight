# ForgeSight — Requirements Traceability (Tata Steel PS §4–§9)

Every Problem-Statement requirement mapped to the concrete artifact that satisfies it, with status.
Legend: ✅ implemented & verified · ◐ implemented with a stated caveat · ⏸ designed, out of build scope.

## §6 Functional Requirements
| FR | Requirement | Status | Where it lives |
|----|-------------|--------|----------------|
| FR-1 | Contextual reasoning via LLM/SLM (merit: fine-tune; APIs allowed) | ✅ | SLM-first runtime `backend/agent/synthesis.py` (Ollama Qwen2.5-3B, `format=`-constrained); **hybrid serving** — local = fine-tuned Qwen via Ollama (`finetune/colab_train.py` QLoRA on T4 → GGUF → `ollama create qwen-forgesight`), public = **Groq** fallback (no cloud GPU); base-vs-FT eval `finetune/03_evaluate_vs_base.py` gates promotion |
| FR-2 | Knowledge integration over manuals/SOPs/records/logs | ✅ | Hybrid metadata-filtered RAG `backend/tools/rag.py` over `doc_chunks`; **governed text-to-SQL** `backend/tools/text_to_sql.py` for analytical/aggregate questions over curated views |
| FR-3 | Natural-language, multi-turn, context-aware | ✅ | `/chat` + LangGraph checkpointer (thread = session); history summarization in `synthesis.py` |
| FR-4 | Explainable, traceable recommendations | ✅ | Citation-existence guardrail `backend/agent/governance.py`; Evidence Trail chips → `/evidence` drawer; visible SQL as citation |
| FR-5 | Abnormality detection · early warning · failure prediction | ✅ | `ml/anomaly` live on sensors (IsolationForest+EWMA); **real held-out inference** served for `ml/defect` (live LightGBM, `analyze_defect`), `ml/failure_classifier` (`predict_failure`), `ml/azure_pdm` (`predict_pdm_24h`), `ml/rul` (`rul_benchmark`) — all exposed via **`GET /models/scorecard`** + dashboard panel; scheduler `backend/scheduler/health_scan.py` raises alerts |
| FR-6 | Feedback-driven improvement | ✅ | `POST /feedback` (up/down/fixed) **changes future answers**: `down` demotes the cited record in `match_history` (re-rank), `fixed` injects the engineer-confirmed cause as a synthesis few-shot exemplar (`backend/tools/feedback_store.py`) + flips `breakdown_history.verified=true` + logbook; proven by `backend/tests/test_feedback_loop.py` |
| FR-7 | Real-time alerting & notifications | ✅ | Background scan started in FastAPI `lifespan` behind `ENABLE_SCHEDULER` (every `SCHEDULER_INTERVAL_SECONDS`) → `alerts` table → `/alerts` → frontend alert feed/toast; severity rules in `health_scan.py` |

## §4 Expected Inputs
| Input | Status | Where |
|-------|--------|-------|
| Delay logs / fault messages / failure reports / breakdown records | ✅ | `breakdown_history`, `doc_chunks(report)`, fault-code extraction in `pipelines.py` |
| Sensor summaries / anomaly alerts / condition indicators | ✅ | `sensor_readings`, `equipment_health`, `alerts` |
| Manuals / SOPs / maintenance records / spares (availability + lead time) | ✅ | `doc_chunks(manual,sop)`, `spares` table + `check_spares` |
| NL queries / scenario prompts / multi-turn follow-ups | ✅ | Copilot sidebar + `/chat` |

## §5 Expected Outputs
| Output | Status | Where |
|--------|--------|-------|
| Fault diagnosis · root-cause analysis | ✅ | `DiagnosisCard` (Diagnostic pipeline) |
| RUL prediction | ✅ | `RULEstimate` (Reliability pipeline, trend extrapolation; C-MAPSS validates method) |
| Early warning of catastrophic failure | ✅ | scheduler CRITICAL alert (RUL < spares lead time) |
| Process-defect detection | ✅ | `ml/defect` (LightGBM, leakage-safe) + `analyze_defect` — live inference on a real held-out Steel Plates row (no zero-vector stub) |
| Risk classification (low→critical) · urgency · bottleneck priority | ✅ | `PriorityCard` (deterministic `score_priority`) |
| Step-by-step recommendations · immediate actions · long-term monitoring | ✅ | `ChecklistCard` (LOTO-first, guardrail-enforced) + WaitAssessment monitoring plan |
| Spare procurement strategy | ✅ | Planner pipeline `check_spares` → `procurement_rule` → HITL reservation |
| Structured maintenance reports · abnormal-alert reports · decision summaries | ✅ | `backend/tools/reports.py` (ReportLab) → `/reports/alert`, `/reports/shift-summary` |
| Digital maintenance logbook (optional enhancement) | ✅ | `logbook` table, written on `fixed` feedback |

## §1.9 Governance / trust (the differentiator)
| Property | Status | Where |
|----------|--------|-------|
| Governed multi-agent graph (Authority · Controller · Guardrails · State) | ✅ | `backend/agent/governance.py` |
| 5 chartered agents (Diagnostic · Reliability · Supervisor · Planner · **Analyst**) | ✅ | `AGENT_CHARTERS`, `pipelines.py` |
| HITL: COMMIT ⇒ human_gate interrupt; agents propose, humans commit | ✅ | `/chat/approve`, Planner pipeline |
| Audited allow+deny on every authority decision | ✅ | `audit_log`, `AgentAuthority` |
| On-prem capable SLM (no plant data leaves the network) | ✅ | Ollama runtime; hosted API is an optional cloud fallback |

## §9 Deliverables
| Deliverable | Status | Where |
|-------------|--------|-------|
| Source code of working prototype | ✅ | this repo |
| Architecture / tech-stack / data-flow / model design doc | ✅ | `docs/architecture.md`, `docs/finetune.md`, this file |
| Alerting & prediction logic | ✅ | `health_scan.py`, `ml/*`, `docs/assumptions_limitations.md` |
| Assumptions & limitations | ✅ | `docs/assumptions_limitations.md` |
| Install / configure / run docs | ✅ | `README.md`, `docs/DEPLOY.md` |
| Sample input & output demonstration | ✅ | `docs/demo_script.md`; per-model `ml/*/test.csv`→`submission.csv` |
| Screen recording | ☐ user-recorded | `docs/demo_script.md` choreography |

## Caveats (honest)
- **Fine-tune** runs on Colab T4 (`finetune/colab_train.py`, reproducible) → GGUF → local Ollama
  `qwen-forgesight`; promotion gated by `finetune/03_evaluate_vs_base.py`. The public Railway URL has
  no GPU, so it uses the **Groq** fallback — hybrid serving is stated, not hidden.
- **Live demo, de-canned.** `DEMO_MODE` defaults **false** so `/chat` runs the real governed pipeline
  (genuine citations). The golden card is now an **error/timeout fallback only** (`AgentController._error_fallback`).
- **Benchmark second-opinions.** failure/azure/RUL XGBoost models surface **real held-out inferences**
  via `/models/scorecard`; they are benchmark-validated, not per-equipment sensor models (honest framing).
- **Out of build scope** (designed, not built): Admin/Plant `/simulate` UI screens, Langfuse
  tracing, persistent semantic cache — see `docs/assumptions_limitations.md`.
