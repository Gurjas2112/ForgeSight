# ForgeSight — Requirements Traceability (Tata Steel PS §4–§9)

Every Problem-Statement requirement mapped to the concrete artifact that satisfies it, with status.
Legend: ✅ implemented & verified · ◐ implemented with a stated caveat · ⏸ designed, out of build scope.

## §6 Functional Requirements
| FR | Requirement | Status | Where it lives |
|----|-------------|--------|----------------|
| FR-1 | Contextual reasoning via LLM/SLM (merit: fine-tune; APIs allowed) | ✅ | SLM-first runtime `backend/agent/synthesis.py` (Ollama Qwen2.5-3B, `format=`-constrained); OpenAI hosted fallback for cloud; **fine-tune pipeline** `finetune/` (Unsloth QLoRA, 40-pair gated dataset) — base ships per promotion rule |
| FR-2 | Knowledge integration over manuals/SOPs/records/logs | ✅ | Hybrid metadata-filtered RAG `backend/tools/rag.py` over `doc_chunks`; **governed text-to-SQL** `backend/tools/text_to_sql.py` for analytical/aggregate questions over curated views |
| FR-3 | Natural-language, multi-turn, context-aware | ✅ | `/chat` + LangGraph checkpointer (thread = session); history summarization in `synthesis.py` |
| FR-4 | Explainable, traceable recommendations | ✅ | Citation-existence guardrail `backend/agent/governance.py`; Evidence Trail chips → `/evidence` drawer; visible SQL as citation |
| FR-5 | Abnormality detection · early warning · failure prediction | ✅ | `ml/anomaly` (IsolationForest+EWMA), `ml/rul` (C-MAPSS), `ml/failure_classifier` (AI4I), `ml/defect` (Steel Plates), **`ml/azure_pdm`** (Azure PdM 24h-ahead), `ml/bearing_features`; scheduler `backend/scheduler/health_scan.py` raises alerts |
| FR-6 | Feedback-driven improvement | ✅ | `POST /feedback` (up/down/fixed); `fixed` → `breakdown_history.verified=true` (green chip) + logbook; frontend thumbs + "This fixed it" |
| FR-7 | Real-time alerting & notifications | ✅ | APScheduler scan → `alerts` table → `/alerts` → frontend alert feed/toast; severity rules in `health_scan.py` |

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
| Process-defect detection | ✅ | `ml/defect` + `analyze_defect` tool |
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
| Architecture / tech-stack / data-flow / model design doc | ✅ | `forgesight-v3-final.md`, `BUILD_GUIDE.md`, this file |
| Alerting & prediction logic | ✅ | `health_scan.py`, `ml/*`, `docs/assumptions_limitations.md` |
| Assumptions & limitations | ✅ | `docs/assumptions_limitations.md` |
| Install / configure / run docs | ✅ | `README.md`, `docs/DEPLOY.md` |
| Sample input & output demonstration | ✅ | `docs/demo_script.md`; per-model `ml/*/test.csv`→`submission.csv` |
| Screen recording | ☐ user-recorded | `docs/demo_script.md` choreography |

## Caveats (honest)
- **Fine-tune** runs on Colab/GPU; runtime ships base Qwen under constrained decoding (citation
  compliance is structural). Promotion rule in `finetune/export/README.md`.
- **Cloud synthesis** uses the OpenAI fallback; the provided key authenticates but has **no quota**,
  so free-form generation on the public URL degrades to the golden demo cache until billing is added.
  Locally, synthesis runs live on Ollama. (`docs/assumptions_limitations.md`)
- **Out of build scope** (designed, not built): Reports/Admin/Plant `/simulate` UI screens, Langfuse
  tracing, semantic cache — see `docs/assumptions_limitations.md`.
