# ForgeSight — SFT Dataset Specification (SLM-First Runtime)
### Fine-tune target: Qwen2.5-3B-Instruct (or 7B if VRAM rehearsal allows) · Unsloth QLoRA · Colab T4
**Purpose:** in the SLM-first architecture the fine-tuned model carries *all* runtime LLM duties — intent classification, every card-type synthesis, repair, and report prose. This dataset is therefore a **core-path deliverable (Phase 0)**, not a merit stretch goal.

---

## 1. What the model must learn (task inventory = runtime LLM call sites)

| # | Task | Runtime call site | Output contract |
|---|---|---|---|
| T1 | Intent + query-class classification | classify_intent node | `{"intent": <enum-9>, "query_class": <enum-3>}` (constrained decode over enum) |
| T2 | DiagnosisCard synthesis | Diagnostic pipeline | DiagnosisCard JSON: fault, confidence∈{High,Medium,Low}, ranked root_causes[] each with citation_refs[] |
| T3 | ChecklistCard synthesis | Diagnostic pipeline (SOP intents) | steps[] with `safety:true` LOTO steps FIRST, expected values, citation_refs |
| T4 | WaitAssessmentCard synthesis | parallel fan-out join (Scenario B) | verdict∈{yes,yes_with_conditions,no}, margin math fields, monitoring_plan, procurement_callout — all numbers copied from tool_results, never computed |
| T5 | RiskCard / urgency narration | Reliability/Supervisor pipelines | risk_level enum + one-line justification tied to citations |
| T6 | Priority narration | Supervisor pipeline | prose explaining a PriorityResult — **score fields copied verbatim from the matrix tool** |
| T7 | Spares/procurement narration | Planner pipeline | SparesCard + procurement_rule narration; proposal text for COMMIT items |
| T8 | Report sections | draft_shift_summary / alert report | exec_summary + per-issue paragraphs from provided results (template fills the structure) |
| T9 | Repair | repair node | input = previous bad card + violations[]; output = corrected card |
| T10 | Insufficient-evidence refusal | any synthesis | when citations are empty/irrelevant: `{"card_type":"no_evidence", ...}` — never invent |

## 2. Volume & mix (~2,150 pairs · 90/10 train/eval, stratified by task)

T1: 300 · T2: 400 · T3: 250 · T4: 200 · T5: 150 · T6: 150 · T7: 150 · T8: 200 · T9: 150 · T10: 100 · multi-turn follow-up variants (pronoun resolution, "what about the other cause?"): 100. Phrasing diversity per task: formal, terse shop-floor, typo-laden, and Indian-English colloquial variants of the same underlying query.

## 3. Format (chat JSONL, Qwen chat template, TRL SFTTrainer)

```json
{"messages": [
  {"role": "system", "content": "<persona prompt for the relevant agent — VERBATIM from AGENT_CHARTERS>"},
  {"role": "user", "content": "<CONTEXT BLOCK (see §4)>\n\nUSER QUERY: how do I check the braking resistor?"},
  {"role": "assistant", "content": "{\"card_type\":\"checklist\", ...valid JSON only...}"}
]}
```

## 4. Input construction — the one rule that decides success

**The context block serializer is a single shared module (`prompt_builder.py`) imported by BOTH the data-generation script and the runtime.** Equipment header, tool_results JSON, citations list (id+ref+excerpt), and history summary must be byte-format-identical between training and inference — train/serve distribution shift is the #1 silent killer of small fine-tunes. Static persona first, volatile fields last (preserves prefix-cache hits at runtime too).

Context block contents per sample: `EQUIPMENT:` line · `TOOL_RESULTS:` compact JSON (real outputs from your deterministic/ML tools run against the synthetic corpus — not hand-written) · `CITATIONS:` numbered list (only these refs may be cited) · `HISTORY:` 1–3 line summary for multi-turn samples.

## 5. Generation pipeline (hosted model, dev-time only — sovereignty intact)

1. Seed scenarios from the synthetic corpus: 6 equipment × fault taxonomy × {reactive, proactive, planning} situations.
2. Run the REAL tools (RAG, ML artifacts, matrix, procurement rule) to produce genuine tool_results + citations per scenario.
3. Prompt Claude/GPT per task type: "Given this context block, produce the target card JSON obeying <schema>. Cite only from CITATIONS. Copy all numbers from TOOL_RESULTS." Temperature 0.7 for query phrasing variety, 0.2 for the answer.
4. For T9: deliberately corrupt good cards (drop a citation, reorder safety steps, break an enum) → violations list → corrected card.
5. For T10: scenarios with empty/irrelevant retrieval → no_evidence card.
6. Dedupe near-identical pairs (embedding cosine >0.97).

## 6. Quality gates

**Automated (100% of samples):** JSON parses · validates against the card schema · `citation_refs ⊆ CITATIONS` · enums legal · every numeric field appears verbatim in TOOL_RESULTS · safety-first ordering in checklists. Reject-and-regenerate failures.
**Manual (50-sample stratified review — non-negotiable):** checklist per sample: schema ✓ · citations honest ✓ · numbers traceable ✓ · LOTO first ✓ · confidence justified ✓ · prose plant-plausible ✓ · refusals genuinely warranted ✓. Bad synthetic labels are the #1 reason hackathon fine-tunes underperform base models.

## 7. Training & export
Unsloth QLoRA: r=16, alpha=16, lr 2e-4, 2–3 epochs, max_seq 4096, packing on, Colab T4. Export both: `save_pretrained_gguf` Q4_K_M → Ollama (primary), `save_pretrained_merged` → vLLM (⭐ LMCache path). Serve with Ollama `format=<json schema>` constrained decoding — structural validity guaranteed by the decoder; the fine-tune buys *semantic* quality.

## 8. Evaluation (eval split + DeepEval)
Eval-split metrics: intent accuracy (T1) · unconstrained JSON-validity rate (reported even though runtime is constrained) · field-level accuracy · citation-subset compliance · number-fidelity rate. Then DeepEval golden set base-vs-fine-tuned → the FR-1 merit table. Promotion rule: fine-tune ships only if it beats base Qwen on citation compliance AND number fidelity; otherwise base + few-shot ships and the fine-tune is presented as in-progress.
