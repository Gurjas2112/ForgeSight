# ForgeSight — Architecture

The authoritative architecture document is [`../forgesight-v3-final.md`](../forgesight-v3-final.md)
(full-stack system design, data flow, model design, alerting/prediction logic, PS traceability).

This file is the submission-facing pointer (PS §9). Implementation status by pass is tracked in
the root [`README.md`](../README.md); the executable build order is
[`../BUILD_GUIDE.md`](../BUILD_GUIDE.md).

## Pass 1 — what is built and proven
- **Datasets/corpus** (`data/`): NASA C-MAPSS / AI4I / UCI Steel Plates downloaders; the synthetic
  steel sensor layer (6 equipment, injected fan-bearing ramp + F3 VFD trip); RAG corpus
  (SOPs + breakdown records, embedded with nomic-embed-text).
- **Governed graph** (`backend/agent/`): `AgentController` (LangGraph) with the Diagnostic charter
  **pipeline** (deterministic tool sequence, not a ReAct loop), `AgentAuthority` (charters/budgets/
  audited allow-deny), `AgentGuardrails` (citation-existence · LOTO-first · matrix-provenance),
  constrained-decode SLM synthesis (Ollama Qwen2.5-3B, `format=<schema>`).
- **Trust tiers**: Supabase schema + RLS (Tier 1), charter governance + audit_log (Tier 2),
  code-level output guardrails (Tier 3).

## Key implementation decision (recorded)
The provided `agent_governance.py` modelled sub-agents as `create_react_agent` graphs; the design
text mandates **deterministic charter pipelines**. `backend/agent/pipelines.py` resolves this:
each agent is a `RunnableLambda` running its charter's fixed tool order with Authority re-checked
(and audited) before each call — same governance, no LLM tool-selection. The SLM is invoked only
at `synthesize`/`repair` under constrained decoding.
