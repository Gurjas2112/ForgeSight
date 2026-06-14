# ForgeSight — Sample Input / Output (golden cases)

PS §9 deliverable. Each case is the literal graph input and the validated card output. Pass 1
covers **Scenario A (reactive diagnosis)** end-to-end; B/C land in later passes.

---

## A1 — Reactive diagnosis (Diagnostic pipeline)

**Input**
```
equipment_id: hsm-f3-stand
query:        "Diagnose the F3 stand — it tripped on fault 0247."
user:         engineer
```

**Governed path** (from `scripts/diagnose_f3.py`)
```
ingest_and_authorize → cache_lookup (miss) → classify_intent (intent=diagnosis, class=knowledge)
→ diagnostic_agent pipeline:
     → retrieve_rag (manuals/SOPs)   [audit: ALLOW diagnostic_agent::retrieve_rag]
     → match_history (verified-first) [audit: ALLOW diagnostic_agent::match_history]
→ synthesize (SLM, format=DiagnosisCard, citation_refs constrained to retrieved set)
→ guardrail_validate (PASS: schema · citations exist · LOTO N/A)
→ respond
```

**Output — DiagnosisCard** (abridged from a real run on base Qwen2.5-3B)
```json
{
  "card_type": "diagnosis",
  "fault": "HSM-F3-VFD-0247",
  "confidence": "High",
  "summary": "The F3 stand tripped due to a braking-resistor element open-circuit; regen energy was not dissipated during deceleration, causing repeated DC-bus overvoltage trips.",
  "root_causes": [
    {"rank": 1, "cause": "Braking resistor element open-circuit; regen energy not dissipated",
     "confidence": "High", "citation_refs": ["BR-2024-0312"]},
    {"rank": 2, "cause": "Deceleration ramp set too aggressive",
     "confidence": "Medium", "citation_refs": ["BR-2024-0155"]}
  ],
  "citation_refs": [
    "SOP-HSM-ELEC-09 — Lockout / Tagout", "SOP-HSM-ELEC-09 — Resistance Measurement",
    "SOP-HSM-ELEC-09 — Restoration", "BR-2024-0155", "BR-2024-0312"
  ]
}
```

**Evidence (every ref exists in retrieved context — the citation-existence guardrail):**
`BR-2024-0312` (verified, same stand, DC-bus overvoltage → braking resistor open-circuit) and
`BR-2024-0155` (same fault code, decel-ramp cause) from `match_history`; `SOP-HSM-ELEC-09`
sections from `retrieve_rag`.

---

## A2 — Insufficient evidence → honest refusal (no fabrication)

**Input:** a query about an equipment with no matching corpus (`caster-1`, obscure symptom).
**Output:** `{"card_type": "no_evidence", "message": "I couldn't find supporting manuals, SOPs,
or records for that…"}` — the synthesis layer refuses when retrieval is empty; the guardrail
independently blocks any uncited claim.

---

## A3 — Out-of-charter action → denied + audited

If an agent attempts a tool outside its charter (e.g. Diagnostic calling `score_priority`),
`AgentAuthority.check_tool` raises `AuthorityError`, an **ALLOW=false** row is written to
`audit_log` with reason `tool_not_in_charter`, and the controller returns a `denied` card. This
is the staged "denied-action" row for the Admin Console closing beat.

---

### How to reproduce
```bash
bash scripts/local_pg.sh                 # or set DATABASE_URL to Supabase
export DATABASE_URL=postgresql://postgres:forgesight@localhost:5433/forgesight
uv run python backend/db/apply_migrations.py
uv run python scripts/diagnose_f3.py
```
