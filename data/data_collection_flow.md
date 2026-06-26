# Data Collection Flow — ForgeSight

ForgeSight's data layer combines **public benchmark datasets** (to validate ML methods on real data),
**physics-shaped synthetic plant data** (the digital-twin sensor stream), and a **RAG knowledge corpus**
(manuals, SOPs, breakdown records). This document maps where each dataset comes from, how it is
processed, and where it lands.

```
            ┌────────────── data/raw/ (public benchmarks) ──────────────┐
fetch_data → cmapss · ai4i · azure_pdm · steel_plates · cwru · ims      │→ ml/ training
            └───────────────────────────────────────────────────────────┘
            ┌────────────── data/synthetic/ ──────────────┐
generate_sensors → sensor_readings.csv · breakdown_history.json         │→ anomaly model + DB seed
            └──────────────────────────────────────────────┘
            ┌────────────── data/corpus/ ─────────────────┐
seed_corpus → corpus_ingest.sql (pgvector INSERTs)         │→ doc_chunks (RAG)  +  finetune SFT
            └──────────────────────────────────────────────┘
```

---

## 1. Public benchmark datasets — `data/raw/`

Fetched by `data/fetch_data.py` (uses `ucimlrepo` / direct download). Each maps to one ML model and a
problem-statement input class (condition monitoring / failure logs).

| Dir | Dataset | Shape | Feeds |
|---|---|---|---|
| `cmapss/` | NASA C-MAPSS FD001 (turbofan run-to-failure) | 100 train + 100 test units | RUL regression (`ml/rul`) |
| `ai4i/` | AI4I 2020 predictive maintenance | 10,000 × 14 | failure classifier (`ml/failure_classifier`) |
| `azure_pdm/` | Microsoft Azure PdM (telemetry/errors/maint/failures) | 100 machines, ~876k telemetry rows | 24h-ahead failure (`ml/azure_pdm`) |
| `steel_plates/` | UCI Steel Plates Faults | 1,941 × 34 | defect classification (`ml/defect`) |
| `cwru/`, `ims/` | Bearing vibration (CWRU / NASA IMS) | README + committed sample | bearing feature extraction (`ml/bearing_features`) |

These validate the *method* on public data — they are benchmark second-opinions, not per-asset models.

---

## 2. Synthetic plant data — `data/synthetic/`

`generate_sensors.py` produces a **physics-shaped** 30-day stream for 6 steel-plant assets (fans,
caster, furnace, crane, mill) with injected degradation:

- `sensor_readings.csv` — 17,280 rows × 13 cols (vibration_de/nde, bearing_temp, motor_current, rpm,
  load_pct, …). Trains the anomaly model and seeds `sensor_readings`.
- `breakdown_history.json` — 23 labelled failure events (fault_code, root_cause, downtime_hrs). Seeds
  `breakdown_history` and supplies exemplars for RAG + the SFT dataset.

Deterministic (`seed=42`) so the twin and demo are reproducible.

> **Honesty note:** there is no public real-time steel-plant sensor feed; this stream is a simulation.
> The governance, ML inference and reasoning that run *on top of it* are real.

---

## 3. RAG knowledge corpus — `data/corpus/`

`seed_corpus.py` builds the searchable knowledge base the Diagnostic agent cites:

1. **Sources:** OEM manuals (PDF, parsed with PyMuPDF), synthetic SOPs (markdown), breakdown records,
   spares (SQL).
2. **Chunking:** structure-aware — section headers → chunks, fault tables → one row per fault code,
   each tagged `doc_type ∈ {manual, sop, report}` with a stable `section_ref`.
3. **Embedding:** `nomic-embed-text` (768-dim) at ingest time.
4. **Output:** `corpus_ingest.sql` — `INSERT` statements into `doc_chunks` (applied by
   `backend/db/apply_migrations.py`).

**Real OEM PDFs (ingested):** `data/synthetic/manuals/` holds the actual manufacturer manuals,
fetched live and parsed with PyMuPDF into `doc_type='manual'` chunks:

| File (stem) | Source | Maps to |
|---|---|---|
| `abb_acs880.pdf` | ABB ACS880 primary control firmware manual (VFD) | `hsm-f3-stand` |
| `skf_22230.pdf` | SKF Bearing Maintenance Handbook | `sinter-fan-2` |
| `fan_om.pdf` | Centrifugal Fan Installation/Operation/Maintenance manual | `sinter-fan-2` |

The PDFs are **gitignored** (large binaries) but their parsed content lives in `doc_chunks`. Current
corpus: **~390 doc_chunks** (349 real manual chunks + 23 breakdown records + 18 SOP procedures). `--max-pages`
/ `--max-manual-chunks` cap very large handbooks so the ingest stays a sane size.

```bash
# 1) fetch the OEM PDFs into data/synthetic/manuals/  (abb_acs880.pdf, skf_22230.pdf, fan_om.pdf)
# 2) chunk + embed (nomic-embed-text via Ollama) → corpus_ingest.sql
uv run python data/corpus/seed_corpus.py \
  --pdf-dir data/synthetic/manuals --out-sql data/corpus/corpus_ingest.sql \
  --max-pages 80 --max-manual-chunks 150
# 3) apply to the DB (psql $DATABASE_URL -f corpus_ingest.sql, or backend/db/apply_migrations.py)
```

Retrieval is hybrid (vector + full-text) via `backend/tools/rag.py`; it degrades to full-text-primary
when no embedding backend is reachable (e.g. cloud demo).

---

## 4. From corpus to fine-tuning

The same corpus + real backend tools generate the supervised fine-tune pairs (so the SLM learns to
narrate over *exactly* the evidence it will see at runtime). The serializer in
`finetune/dataset/prompt_builder.py` is byte-identical to the runtime `backend/agent/prompt_builder.py`.
See [`../finetune/finetuning_workflow.md`](../finetune/finetuning_workflow.md).

---

## 5. End-to-end refresh

```bash
uv run python data/fetch_data.py                      # public benchmarks → data/raw/
uv run python data/synthetic/generate_sensors.py      # synthetic stream + breakdowns
uv run python data/corpus/seed_corpus.py --out-sql data/corpus/corpus_ingest.sql
uv run python backend/db/apply_migrations.py          # load corpus + seeds into Postgres
```

Downstream consumers: [`../ml/Ml_workflow.md`](../ml/Ml_workflow.md) (training) and
[`../backend/database_setup.md`](../backend/database_setup.md) (storage).
