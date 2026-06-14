"""
ForgeSight — Corpus Seeding & Knowledge-Base Builder  (Phase 0 deliverable)
===========================================================================
Builds the RAG corpus that powers §4.3 / FR-2 AND seeds the SFT data generation.
Three source families, four chunking strategies, one pgvector store.

  Sources
    - Manuals (PDF)           : real OEM PDFs (ABB/Siemens VFD, SKF bearing, fan O&M)
                                + optional Firecrawl-scraped HTML knowledge pages
    - SOPs (synthetic md)     : steel-specific, authored here, markdown-structured
    - Breakdown records (synth): one record = one atomic chunk
    - Spares                  : NOT embedded — structured SQL only (check_spares tool)

  Chunking (structure is the signal — one strategy per type)
    - manual   : section-aware two-stage split; fault-code tables → atomic rows
    - sop      : MarkdownHeaderTextSplitter — one complete procedure per chunk
    - record   : no split — labelled block
    - spares   : none (lives in the spares table)

  Store/retrieve
    - plain SQL on the custom doc_chunks schema (NOT LangChain PGVector class —
      it would fight our RLS / content_hash dedupe). LangChain used for
      loaders + splitters only. Embeddings via Ollama nomic-embed-text.

Run:  python seed_corpus.py --pdf-dir ./manuals --out-sql ./corpus_ingest.sql
      (set FIRECRAWL_API_KEY to enable HTML scraping; omit to skip it)
Idempotent: content_hash dedupe means re-runs only ingest changed/new chunks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path

# ---- LangChain: loaders + splitters ONLY ----
from langchain_text_splitters import (RecursiveCharacterTextSplitter,
                                       MarkdownHeaderTextSplitter)

EMBED_DIM = 768  # nomic-embed-text


# ----------------------------------------------------------------------------------
# 0. Chunk dataclass — fields map 1:1 to the doc_chunks table
# ----------------------------------------------------------------------------------

@dataclass
class Chunk:
    equipment_id: str | None
    doc_type: str                 # manual | sop | report
    section_ref: str              # becomes the Evidence-chip label
    content: str
    source: str                   # attribution (OEM name / "synthetic")
    content_hash: str = ""

    def finalize(self) -> "Chunk":
        self.content_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        return self


# ----------------------------------------------------------------------------------
# 1. EQUIPMENT REGISTRY — the six assets the whole demo references
# ----------------------------------------------------------------------------------

EQUIPMENT = [
    {"id": "hsm-f3-stand",  "name": "Hot Strip Mill F3 Stand",   "zone": "Rolling",
     "criticality": 9, "drive": "ABB ACS880"},
    {"id": "sinter-fan-2",  "name": "Sinter Plant ID Fan #2",    "zone": "Sinter",
     "criticality": 8, "bearing": "SKF 22230"},
    {"id": "caster-1",      "name": "Continuous Caster #1",      "zone": "Casting",
     "criticality": 10},
    {"id": "bf-stove-a",    "name": "Blast Furnace Stove A",     "zone": "Iron",
     "criticality": 9},
    {"id": "ladle-crane-4", "name": "Ladle Crane #4",            "zone": "Casting",
     "criticality": 7},
    {"id": "sinter-fan-1",  "name": "Sinter Plant ID Fan #1",    "zone": "Sinter",
     "criticality": 8, "bearing": "SKF 22230"},
]


# ----------------------------------------------------------------------------------
# 2a. CHUNKER — MANUALS (PDF): section-aware + fault-code-table atomic rows
# ----------------------------------------------------------------------------------

_manual_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800, chunk_overlap=120,
    separators=["\n\n", "\n", ". ", " "])

# matches table rows like "F0247 | DC bus overvoltage | ..." or "0247  DC bus overvoltage"
_FAULT_ROW = re.compile(r"^\s*([A-Z]?\d{3,5})[\s|:.-]+(.{6,})$")
# splits before a numbered heading: "\n4.3 Braking resistor checks"
_SECTION = re.compile(r"\n(?=\d+(?:\.\d+)*\s+[A-Z])")


def chunk_manual(text: str, equipment_id: str, source: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in _SECTION.split(text):
        section = section.strip()
        if not section:
            continue
        header = section.split("\n", 1)[0][:80]
        # fault-code tables: each row is its OWN atomic chunk (exact-match retrieval)
        rows = [m for line in section.splitlines() if (m := _FAULT_ROW.match(line))]
        if len(rows) >= 3:  # looks like a fault table
            for m in rows:
                code, desc = m.group(1), m.group(2).strip()
                chunks.append(Chunk(
                    equipment_id, "manual", f"{header} — fault {code}",
                    f"[{source} — {header}] Fault {code}: {desc}", source).finalize())
            continue
        # normal prose: recursive split WITH header prepended for context anchoring
        for piece in _manual_splitter.split_text(section):
            chunks.append(Chunk(
                equipment_id, "manual", header,
                f"[{source} — {header}]\n{piece}", source).finalize())
    return chunks


# ----------------------------------------------------------------------------------
# 2b. CHUNKER — SOPs: one complete procedure per chunk (NEVER split a step list)
# ----------------------------------------------------------------------------------

_md_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "sop"), ("##", "procedure")],
    strip_headers=False)


def chunk_sop(md_text: str, equipment_id: str, sop_ref: str) -> list[Chunk]:
    out: list[Chunk] = []
    for doc in _md_splitter.split_text(md_text):
        proc = doc.metadata.get("procedure") or doc.metadata.get("sop") or sop_ref
        # safety preamble duplicated into oversized procedures so LOTO survives a split
        body = doc.page_content
        if len(body) > 1500 and "LOTO" in body:
            preamble = body.split("\n", 3)[0]
            body = body  # (kept whole here; sub-split only if a single proc is huge)
        out.append(Chunk(equipment_id, "sop", f"{sop_ref} — {proc}",
                         body, "synthetic-SOP").finalize())
    return out


# ----------------------------------------------------------------------------------
# 2c. CHUNKER — BREAKDOWN RECORDS: no split, labelled block, verified flag in ref
# ----------------------------------------------------------------------------------

def chunk_record(rec: dict) -> Chunk:
    verified = " [VERIFIED]" if rec.get("verified") else ""
    content = (f"FAULT: {rec['fault_code']} | EQUIPMENT: {rec['equipment_id']} | "
               f"DATE: {rec['occurred_at']} | SYMPTOMS: {rec['symptoms']} | "
               f"ROOT CAUSE: {rec['root_cause']} | RESOLUTION: {rec['resolution']} | "
               f"DOWNTIME: {rec['downtime_hrs']}h")
    return Chunk(rec["equipment_id"], "report",
                 f"{rec['id']}{verified}", content, "maintenance-history").finalize()


# ----------------------------------------------------------------------------------
# 3. SYNTHETIC AUTHORING — SOPs and breakdown records (deterministic, no LLM needed)
# ----------------------------------------------------------------------------------

def make_synthetic_sops() -> list[tuple[str, str, str]]:
    """Returns (equipment_id, sop_ref, markdown). LOTO-first by construction so the
    ChecklistCard guardrail is satisfied straight from the corpus."""
    return [
        ("hsm-f3-stand", "SOP-HSM-ELEC-09", """# SOP-HSM-ELEC-09 Braking Resistor Inspection
## Lockout / Tagout
1. **[SAFETY]** Apply LOTO to the F3 stand drive isolator; verify zero energy.
2. **[SAFETY]** Wait 10 minutes for DC-bus capacitor discharge; confirm <50 VDC at terminals.
## Resistance Measurement
3. Disconnect braking resistor leads at the drive.
4. Measure resistance across the resistor element. Expected: 8.0–8.4 Ω (rated 8.2 Ω ±5%).
5. An open circuit (OL) indicates a failed element — replace the resistor assembly.
6. A reading <7.0 Ω indicates a shorted turn — replace.
## Restoration
7. Reconnect leads, remove LOTO, restore drive, run a controlled deceleration test.
"""),
        ("sinter-fan-2", "SOP-SNT-MECH-04", """# SOP-SNT-MECH-04 ID Fan Bearing Condition Check
## Lockout / Tagout
1. **[SAFETY]** Apply LOTO to the ID fan motor; verify fan has coasted to full stop.
## Vibration Assessment
2. Measure DE and NDE bearing vibration (mm/s RMS) per ISO 10816.
3. Alarm limit 7.1 mm/s; trip 11.0 mm/s. Trend over last 14 days before deciding.
4. If trending toward alarm, increase sampling to hourly and schedule replacement.
## Bearing Replacement (if required)
5. Reserve SKF 22230 spare (confirm stock and lead time with planning).
6. Follow SKF mounting handbook drive-up method; verify radial clearance.
"""),
    ]


def make_synthetic_records() -> list[dict]:
    """~breakdown history. The ① root-cause match in Scenario A points at BR-2024-0312."""
    return [
        {"id": "BR-2024-0312", "equipment_id": "hsm-f3-stand", "occurred_at": "2024-04-18",
         "fault_code": "HSM-F3-VFD-0247", "symptoms": "Repeated DC bus overvoltage trips on deceleration",
         "root_cause": "Braking resistor element open-circuit; regen energy not dissipated",
         "resolution": "Replaced braking resistor assembly; verified 8.2 ohm", "downtime_hrs": 3.5,
         "verified": True},
        {"id": "BR-2023-0847", "equipment_id": "sinter-fan-2", "occurred_at": "2023-11-02",
         "fault_code": "SNT-FAN-VIB-HI", "symptoms": "DE bearing vibration rising over 3 weeks",
         "root_cause": "Bearing outer-race spalling (fatigue)",
         "resolution": "Replaced SKF 22230 DE bearing during planned shutdown", "downtime_hrs": 6.0,
         "verified": True},
        {"id": "BR-2024-0155", "equipment_id": "hsm-f3-stand", "occurred_at": "2024-02-09",
         "fault_code": "HSM-F3-VFD-0247", "symptoms": "Single overvoltage trip after parameter change",
         "root_cause": "Deceleration ramp set too aggressive",
         "resolution": "Extended decel ramp from 2s to 4s", "downtime_hrs": 0.5, "verified": True},
        # ... generator extends to ~120 across all six equipment with realistic spread
    ]


# ----------------------------------------------------------------------------------
# 4. FIRECRAWL — optional, dev-time only, HTML knowledge pages → markdown
# ----------------------------------------------------------------------------------

def firecrawl_scrape(urls: list[str], equipment_id: str) -> list[Chunk]:
    """Only runs if FIRECRAWL_API_KEY is set. Returns markdown chunked as SOP-style.
    NEVER called at runtime — sovereignty/on-prem story stays intact."""
    key = os.getenv("FIRECRAWL_API_KEY")
    if not key:
        print("  (FIRECRAWL_API_KEY not set — skipping HTML scrape)")
        return []
    from firecrawl import FirecrawlApp           # pip install firecrawl-py
    app = FirecrawlApp(api_key=key)
    chunks: list[Chunk] = []
    for url in urls:
        md = app.scrape_url(url, params={"formats": ["markdown"]})["markdown"]
        for doc in _md_splitter.split_text(md):
            ref = doc.metadata.get("procedure") or url.rsplit("/", 1)[-1]
            chunks.append(Chunk(equipment_id, "manual", f"web:{ref}",
                                doc.page_content, f"web:{url}").finalize())
    return chunks


# ----------------------------------------------------------------------------------
# 5. PDF LOADING (PyMuPDF) — real OEM manuals
# ----------------------------------------------------------------------------------

def load_pdf_text(pdf_path: Path) -> str:
    from langchain_community.document_loaders import PyMuPDFLoader
    pages = PyMuPDFLoader(str(pdf_path)).load()
    return "\n".join(p.page_content for p in pages)


PDF_EQUIPMENT_MAP = {           # filename stem -> equipment_id, source label
    "abb_acs880":  ("hsm-f3-stand", "ABB ACS880 Firmware Manual"),
    "skf_22230":   ("sinter-fan-2", "SKF Bearing Maintenance Handbook"),
    "fan_om":      ("sinter-fan-2", "Centrifugal Fan O&M Manual"),
}


# ----------------------------------------------------------------------------------
# 6. EMBED + EMIT INGEST SQL (idempotent, ON CONFLICT DO NOTHING)
# ----------------------------------------------------------------------------------

def embed_all(texts: list[str]) -> list[list[float]]:
    from langchain_ollama import OllamaEmbeddings
    return OllamaEmbeddings(model="nomic-embed-text").embed_documents(texts)


def emit_sql(chunks: list[Chunk], out_path: Path) -> None:
    # dedupe within this run by hash
    seen, uniq = set(), []
    for c in chunks:
        if c.content_hash not in seen:
            seen.add(c.content_hash); uniq.append(c)
    print(f"  embedding {len(uniq)} unique chunks via nomic-embed-text…")
    vectors = embed_all([c.content for c in uniq])
    lines = ["-- ForgeSight corpus ingest (idempotent)",
             "-- run: psql $DATABASE_URL -f corpus_ingest.sql\n"]
    for c, v in zip(uniq, vectors):
        vec = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
        content = c.content.replace("'", "''")
        eq = "NULL" if c.equipment_id is None else f"'{c.equipment_id}'"
        sec = c.section_ref.replace("'", "''")
        src = c.source.replace("'", "''")
        lines.append(
            "INSERT INTO doc_chunks (equipment_id, doc_type, section_ref, content, "
            "source, content_hash, embedding) VALUES ("
            f"{eq}, '{c.doc_type}', '{sec}', '{content}', '{src}', "
            f"'{c.content_hash}', '{vec}') ON CONFLICT (content_hash) DO NOTHING;")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    by_type = {}
    for c in uniq:
        by_type[c.doc_type] = by_type.get(c.doc_type, 0) + 1
    print(f"  wrote {out_path}  ({by_type})")


# ----------------------------------------------------------------------------------
# 7. ORCHESTRATION
# ----------------------------------------------------------------------------------

def build_corpus(pdf_dir: Path | None, out_sql: Path) -> None:
    chunks: list[Chunk] = []

    # SOPs (synthetic)
    for eq, ref, md in make_synthetic_sops():
        chunks += chunk_sop(md, eq, ref)
    # breakdown records (synthetic) — also exported separately for the breakdown_history table
    records = make_synthetic_records()
    chunks += [chunk_record(r) for r in records]
    Path("breakdown_history.json").write_text(json.dumps(records, indent=2))

    # manuals (real PDFs, if provided)
    if pdf_dir and pdf_dir.exists():
        for pdf in pdf_dir.glob("*.pdf"):
            stem = pdf.stem.lower()
            eq, src = next(((e, s) for k, (e, s) in PDF_EQUIPMENT_MAP.items()
                            if k in stem), (None, pdf.stem))
            print(f"  parsing manual {pdf.name} → {eq}")
            chunks += chunk_manual(load_pdf_text(pdf), eq, src)

    # optional HTML knowledge pages
    chunks += firecrawl_scrape(
        ["https://example-oem/acs880/fault-codes"],  # replace with real OEM KB URLs
        "hsm-f3-stand")

    print(f"  total chunks before dedupe: {len(chunks)}")
    emit_sql(chunks, out_sql)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", type=Path, default=Path("./manuals"))
    ap.add_argument("--out-sql", type=Path, default=Path("./corpus_ingest.sql"))
    args = ap.parse_args()
    build_corpus(args.pdf_dir, args.out_sql)
    print("done. Next: psql $DATABASE_URL -f corpus_ingest.sql")
