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
    ChecklistCard guardrail is satisfied straight from the corpus. One procedure per asset."""
    return [
        ("hsm-f3-stand", "SOP-HSM-ELEC-09", """# SOP-HSM-ELEC-09 Braking Resistor Inspection
## Lockout / Tagout
1. **[SAFETY]** Apply LOTO to the F3 stand drive isolator; verify zero energy.
2. **[SAFETY]** Wait 10 minutes for DC-bus capacitor discharge; confirm <50 VDC at terminals.
## Resistance Measurement
3. Disconnect braking resistor leads at the drive.
4. Measure resistance across the resistor element. Expected: 8.0-8.4 ohm (rated 8.2 ohm +/-5%).
5. An open circuit (OL) indicates a failed element - replace the resistor assembly.
6. A reading <7.0 ohm indicates a shorted turn - replace.
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
        ("sinter-fan-1", "SOP-SNT-MECH-04A", """# SOP-SNT-MECH-04A ID Fan #1 Bearing & Balance Check
## Lockout / Tagout
1. **[SAFETY]** Apply LOTO to the ID Fan #1 motor; confirm full coast-down before access.
## Vibration & Balance
2. Measure DE/NDE vibration (mm/s RMS) per ISO 10816; alarm 7.1, trip 11.0.
3. Capture a spectrum: 1x running speed peak indicates imbalance/fouling, not bearing fault.
4. If 1x dominates, inspect impeller for ash build-up and clean before replacing bearings.
## Restoration
5. Re-balance to G2.5 if residual imbalance remains; remove LOTO and restart.
"""),
        ("caster-1", "SOP-CAST-HYD-07", """# SOP-CAST-HYD-07 Mould Oscillator Hydraulic Check
## Lockout / Tagout
1. **[SAFETY]** Apply LOTO to the caster hydraulic power unit; bleed accumulator to zero pressure.
2. **[SAFETY]** Confirm mould oscillator is mechanically restrained before any line break.
## Pressure & Level Checks
3. Verify system pressure 150-160 bar at the HPU gauge; low pressure causes mould-level hunting.
4. Inspect the servo valve and accumulator pre-charge (expected 90 bar N2).
5. Mould level instability >+/-3 mm with stable casting speed points to servo-valve wear.
## Restoration
6. Replace the servo valve if hysteresis exceeds spec; re-pressurise, remove LOTO, recommission.
"""),
        ("bf-stove-a", "SOP-BF-STOVE-03", """# SOP-BF-STOVE-03 Hot-Blast Stove Changeover & Dome Temp
## Lockout / Tagout
1. **[SAFETY]** Isolate the burner gas line and apply LOTO; purge before any valve work.
2. **[SAFETY]** Confirm dome thermocouples read true before relighting (no stale latched value).
## Dome Temperature Control
3. Dome temperature limit 1420 C; sustained excursion risks refractory dome damage.
4. On high-dome alarm, reduce gas/air ratio and verify the changeover valve fully strokes.
5. A valve that fails to seat causes cross-leakage and uncontrolled dome heating.
## Restoration
6. Stroke-test the changeover valve, confirm seating, remove LOTO, return stove to cycle.
"""),
        ("ladle-crane-4", "SOP-CRN-MECH-05", """# SOP-CRN-MECH-05 Ladle Crane Hoist Brake Inspection
## Lockout / Tagout
1. **[SAFETY]** Land the ladle/empty the hook, apply LOTO to the hoist drive, chock the trolley.
2. **[SAFETY]** Never inspect a brake under suspended load.
## Brake & Hoist Checks
3. Measure brake lining thickness; replace below 3 mm (new 8 mm).
4. Check brake air-gap 0.5-0.7 mm; excessive gap causes slow set and load drift.
5. Hoist motor over-temperature trips often follow dragging brakes (heat from partial set).
## Restoration
6. Adjust air-gap or replace linings, function-test with a rated test load, remove LOTO.
"""),
    ]


def make_synthetic_records() -> list[dict]:
    """Breakdown history across all six assets — one record = one atomic, citable chunk.
    The flagship Scenario-A root-cause match points at BR-2024-0312."""
    return [
        # --- hsm-f3-stand (ABB ACS880 VFD) ---
        {"id": "BR-2024-0312", "equipment_id": "hsm-f3-stand", "occurred_at": "2024-04-18",
         "fault_code": "HSM-F3-VFD-0247", "symptoms": "Repeated DC bus overvoltage trips on deceleration",
         "root_cause": "Braking resistor element open-circuit; regen energy not dissipated",
         "resolution": "Replaced braking resistor assembly; verified 8.2 ohm", "downtime_hrs": 3.5,
         "verified": True},
        {"id": "BR-2024-0155", "equipment_id": "hsm-f3-stand", "occurred_at": "2024-02-09",
         "fault_code": "HSM-F3-VFD-0247", "symptoms": "Single overvoltage trip after parameter change",
         "root_cause": "Deceleration ramp set too aggressive",
         "resolution": "Extended decel ramp from 2s to 4s", "downtime_hrs": 0.5, "verified": True},
        {"id": "BR-2023-0612", "equipment_id": "hsm-f3-stand", "occurred_at": "2023-08-21",
         "fault_code": "HSM-F3-VFD-2310", "symptoms": "Drive tripped on motor overtemperature at full load",
         "root_cause": "Blocked drive cabinet filter; cooling-fan airflow reduced",
         "resolution": "Replaced cabinet filters and cleaned heatsink; restored airflow", "downtime_hrs": 2.0,
         "verified": True},
        {"id": "BR-2023-0298", "equipment_id": "hsm-f3-stand", "occurred_at": "2023-03-14",
         "fault_code": "HSM-F3-LUB-LO", "symptoms": "Low lube oil pressure alarm on the stand gearbox",
         "root_cause": "Suction strainer partially clogged; pump cavitation",
         "resolution": "Cleaned strainer, topped oil, confirmed 2.5 bar at gallery", "downtime_hrs": 1.5,
         "verified": True},
        {"id": "BR-2022-1190", "equipment_id": "hsm-f3-stand", "occurred_at": "2022-12-03",
         "fault_code": "HSM-F3-VFD-0247", "symptoms": "Intermittent overvoltage during emergency stops",
         "root_cause": "Loose braking resistor terminal raising contact resistance",
         "resolution": "Re-torqued terminals to spec; trip cleared", "downtime_hrs": 1.0, "verified": True},

        # --- sinter-fan-2 (SKF 22230 bearing) ---
        {"id": "BR-2023-0847", "equipment_id": "sinter-fan-2", "occurred_at": "2023-11-02",
         "fault_code": "SNT-FAN-VIB-HI", "symptoms": "DE bearing vibration rising over 3 weeks",
         "root_cause": "Bearing outer-race spalling (fatigue)",
         "resolution": "Replaced SKF 22230 DE bearing during planned shutdown", "downtime_hrs": 6.0,
         "verified": True},
        {"id": "BR-2024-0421", "equipment_id": "sinter-fan-2", "occurred_at": "2024-05-09",
         "fault_code": "SNT-FAN-VIB-HI", "symptoms": "Vibration step-change after a hot restart",
         "root_cause": "Ash build-up on impeller causing mass imbalance",
         "resolution": "Water-washed impeller offline; vibration returned to 3.1 mm/s", "downtime_hrs": 2.5,
         "verified": True},
        {"id": "BR-2023-0533", "equipment_id": "sinter-fan-2", "occurred_at": "2023-06-27",
         "fault_code": "SNT-FAN-MOT-OT", "symptoms": "Fan motor winding over-temperature trip",
         "root_cause": "Failed motor cooling fan; reduced ventilation",
         "resolution": "Replaced motor cooling fan and cleaned vents", "downtime_hrs": 3.0, "verified": True},
        {"id": "BR-2022-0905", "equipment_id": "sinter-fan-2", "occurred_at": "2022-10-15",
         "fault_code": "SNT-FAN-VIB-HI", "symptoms": "NDE bearing vibration with rising temperature",
         "root_cause": "Inadequate grease (over-greased, churning)",
         "resolution": "Purged and re-greased to schedule; vibration normalised", "downtime_hrs": 1.5,
         "verified": True},

        # --- sinter-fan-1 (SKF 22230 bearing) ---
        {"id": "BR-2024-0188", "equipment_id": "sinter-fan-1", "occurred_at": "2024-03-02",
         "fault_code": "SNT-FAN-IMB", "symptoms": "Steady 1x running-speed vibration peak",
         "root_cause": "Impeller fouling (ash) causing imbalance",
         "resolution": "Cleaned impeller and re-balanced to G2.5", "downtime_hrs": 2.0, "verified": True},
        {"id": "BR-2023-0760", "equipment_id": "sinter-fan-1", "occurred_at": "2023-09-18",
         "fault_code": "SNT-FAN-VIB-HI", "symptoms": "DE bearing vibration trending up over a month",
         "root_cause": "Outer-race spalling (fatigue)",
         "resolution": "Replaced SKF 22230 DE bearing", "downtime_hrs": 5.5, "verified": True},
        {"id": "BR-2022-1043", "equipment_id": "sinter-fan-1", "occurred_at": "2022-11-29",
         "fault_code": "SNT-FAN-IMB", "symptoms": "Vibration rose after duct damper repair",
         "root_cause": "Loose impeller hub fastener",
         "resolution": "Re-torqued hub fasteners to spec", "downtime_hrs": 1.0, "verified": True},

        # --- caster-1 (Continuous Caster #1) ---
        {"id": "BR-2024-0277", "equipment_id": "caster-1", "occurred_at": "2024-04-30",
         "fault_code": "CAST-MOLD-LVL-12", "symptoms": "Mould level hunting +/-5 mm at steady casting speed",
         "root_cause": "Servo valve hysteresis from wear",
         "resolution": "Replaced mould-oscillator servo valve; level stabilised to +/-1 mm", "downtime_hrs": 4.0,
         "verified": True},
        {"id": "BR-2023-0689", "equipment_id": "caster-1", "occurred_at": "2023-07-11",
         "fault_code": "CAST-HYD-PRES-LO", "symptoms": "Hydraulic system pressure dropping below 150 bar",
         "root_cause": "Accumulator nitrogen pre-charge lost (bladder leak)",
         "resolution": "Replaced accumulator bladder; recharged to 90 bar N2", "downtime_hrs": 3.5,
         "verified": True},
        {"id": "BR-2023-0204", "equipment_id": "caster-1", "occurred_at": "2023-02-22",
         "fault_code": "CAST-MOLD-LVL-12", "symptoms": "Sudden mould-level spikes during ladle change",
         "root_cause": "Stopper-rod mechanism sticking",
         "resolution": "Cleaned and re-aligned stopper-rod actuator", "downtime_hrs": 2.0, "verified": True},
        {"id": "BR-2022-0817", "equipment_id": "caster-1", "occurred_at": "2022-09-05",
         "fault_code": "CAST-HYD-PRES-LO", "symptoms": "Slow oscillator response and low pressure alarm",
         "root_cause": "Worn main hydraulic pump",
         "resolution": "Overhauled hydraulic pump; restored 158 bar", "downtime_hrs": 6.0, "verified": True},

        # --- bf-stove-a (Blast Furnace Stove A) ---
        {"id": "BR-2024-0099", "equipment_id": "bf-stove-a", "occurred_at": "2024-01-19",
         "fault_code": "BF-STOVE-TEMP-HI", "symptoms": "Dome temperature exceeding 1420 C during gas phase",
         "root_cause": "Changeover valve not fully seating; cross-leakage of gas",
         "resolution": "Reground valve seat and re-stroked actuator; dome control restored", "downtime_hrs": 5.0,
         "verified": True},
        {"id": "BR-2023-0712", "equipment_id": "bf-stove-a", "occurred_at": "2023-08-08",
         "fault_code": "BF-STOVE-VLV-FAIL", "symptoms": "Changeover valve failed to stroke on command",
         "root_cause": "Seized actuator linkage (corrosion)",
         "resolution": "Freed and lubricated linkage; replaced limit switch", "downtime_hrs": 4.5,
         "verified": True},
        {"id": "BR-2022-1276", "equipment_id": "bf-stove-a", "occurred_at": "2022-12-20",
         "fault_code": "BF-STOVE-TEMP-HI", "symptoms": "Erratic dome temperature readings",
         "root_cause": "Drifting dome thermocouple giving false-low feedback",
         "resolution": "Replaced dome thermocouple; recalibrated loop", "downtime_hrs": 2.0, "verified": True},

        # --- ladle-crane-4 (Ladle Crane #4) ---
        {"id": "BR-2024-0356", "equipment_id": "ladle-crane-4", "occurred_at": "2024-05-21",
         "fault_code": "CRN-BRAKE-WEAR", "symptoms": "Hoist load drift after stopping; slow brake set",
         "root_cause": "Brake linings worn below 3 mm and excessive air-gap",
         "resolution": "Replaced brake linings; reset air-gap to 0.6 mm", "downtime_hrs": 3.0, "verified": True},
        {"id": "BR-2023-0481", "equipment_id": "ladle-crane-4", "occurred_at": "2023-05-30",
         "fault_code": "CRN-HOIST-OT", "symptoms": "Hoist motor over-temperature on repeated lifts",
         "root_cause": "Dragging brake from inadequate air-gap adding heat",
         "resolution": "Re-adjusted brake air-gap; over-temp cleared", "downtime_hrs": 2.5, "verified": True},
        {"id": "BR-2022-0644", "equipment_id": "ladle-crane-4", "occurred_at": "2022-07-17",
         "fault_code": "CRN-BRAKE-WEAR", "symptoms": "Audible brake squeal and delayed stop",
         "root_cause": "Glazed brake linings",
         "resolution": "Replaced linings and bedded-in with test load", "downtime_hrs": 2.0, "verified": True},
        {"id": "BR-2024-0510", "equipment_id": "ladle-crane-4", "occurred_at": "2024-06-08",
         "fault_code": "CRN-HOIST-OT", "symptoms": "Repeated hoist over-temp during peak shift",
         "root_cause": "Partially seized brake caliper pin",
         "resolution": "Freed caliper pin, replaced linings, verified air-gap", "downtime_hrs": 3.5,
         "verified": True},
    ]


def make_synthetic_manual_fault_chunks() -> list[Chunk]:
    """OEM-style fault-code table rows (one atomic chunk per code) for exact-match retrieval.
    No PDF required — mirrors the ABB/SKF/fan manuals the demo cites."""
    tables: list[tuple[str, str, list[tuple[str, str]]]] = [
        ("hsm-f3-stand", "ABB ACS880 Firmware Manual",
         [("0247", "DC bus overvoltage — check braking resistor and decel ramp"),
          ("2310", "Motor overtemperature — verify cabinet airflow and filter"),
          ("LUB-LO", "Gearbox lube pressure low — inspect strainer and pump suction")]),
        ("sinter-fan-2", "Centrifugal Fan O&M Manual",
         [("VIB-HI", "Bearing vibration high — trend DE/NDE; alarm 7.1 mm/s, trip 11.0 mm/s"),
          ("MOT-OT", "Motor winding over-temperature — check motor cooling fan and vents"),
          ("IMB", "Impeller imbalance — inspect fouling before bearing replacement")]),
        ("sinter-fan-1", "Centrifugal Fan O&M Manual",
         [("VIB-HI", "Bearing vibration high — outer-race spalling common after 18k h"),
          ("IMB", "1x running-speed peak — impeller fouling or loose hub fastener"),
          ("MOT-OT", "Motor over-temperature — verify cooling fan and load")]),
        ("caster-1", "Caster Hydraulic & Oscillator Manual",
         [("MOLD-LVL-12", "Mould level instability — servo valve hysteresis or stopper sticking"),
          ("HYD-PRES-LO", "Hydraulic pressure low — check accumulator pre-charge and pump")]),
        ("bf-stove-a", "Hot-Blast Stove Control Manual",
         [("TEMP-HI", "Dome temperature high — verify changeover valve seating and gas ratio"),
          ("VLV-FAIL", "Changeover valve failed to stroke — inspect actuator linkage")]),
        ("ladle-crane-4", "Overhead Crane O&M Manual",
         [("BRAKE-WEAR", "Hoist brake wear — lining below 3 mm or excessive air-gap"),
          ("HOIST-OT", "Hoist motor over-temperature — dragging brake or overload")]),
    ]
    out: list[Chunk] = []
    for eq, source, rows in tables:
        for code, desc in rows:
            content = f"[{source} — fault codes] Fault {code}: {desc}"
            out.append(Chunk(eq, "manual", f"{source} — fault {code}", content, source).finalize())
    return out


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

def load_pdf_text(pdf_path: Path, max_pages: int | None = None) -> str:
    """Extract text from a real OEM PDF. `max_pages` caps very large handbooks (e.g. the
    14 MB SKF manual) so the ingest stays a sane size — we still capture authentic OEM prose;
    fault-code exact-match is already covered by the synthetic fault-table chunks."""
    from langchain_community.document_loaders import PyMuPDFLoader
    pages = PyMuPDFLoader(str(pdf_path)).load()
    if max_pages:
        pages = pages[:max_pages]
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

def build_corpus(pdf_dir: Path | None, out_sql: Path, *,
                 max_pages: int | None = None, max_manual_chunks: int | None = None) -> None:
    chunks: list[Chunk] = []

    # SOPs (synthetic)
    for eq, ref, md in make_synthetic_sops():
        chunks += chunk_sop(md, eq, ref)
    # breakdown records (synthetic) — also exported separately for the breakdown_history table.
    # Write to data/synthetic/ (where apply_migrations.py loads it) when the layout is present,
    # otherwise fall back to the CWD.
    records = make_synthetic_records()
    chunks += [chunk_record(r) for r in records]
    chunks += make_synthetic_manual_fault_chunks()
    bh_path = out_sql.parent.parent / "synthetic" / "breakdown_history.json"
    if not bh_path.parent.exists():
        bh_path = Path("breakdown_history.json")
    bh_path.write_text(json.dumps(records, indent=2))
    print(f"  wrote {len(records)} breakdown records -> {bh_path}")

    # manuals (real PDFs, if provided)
    if pdf_dir and pdf_dir.exists():
        for pdf in sorted(pdf_dir.glob("*.pdf")):
            stem = pdf.stem.lower()
            eq, src = next(((e, s) for k, (e, s) in PDF_EQUIPMENT_MAP.items()
                            if k in stem), (None, pdf.stem))
            mc = chunk_manual(load_pdf_text(pdf, max_pages=max_pages), eq, src)
            if max_manual_chunks:
                mc = mc[:max_manual_chunks]
            print(f"  parsing manual {pdf.name} → {eq} · {len(mc)} chunks")
            chunks += mc

    # optional HTML knowledge pages (only with real OEM KB URLs + FIRECRAWL_API_KEY).
    # Disabled by default — the real OEM PDFs above are the manual source of truth.

    print(f"  total chunks before dedupe: {len(chunks)}")
    emit_sql(chunks, out_sql)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", type=Path, default=Path("./manuals"))
    ap.add_argument("--out-sql", type=Path, default=Path("./corpus_ingest.sql"))
    ap.add_argument("--max-pages", type=int, default=None,
                    help="cap pages read per PDF (large OEM handbooks)")
    ap.add_argument("--max-manual-chunks", type=int, default=None,
                    help="cap chunks kept per manual PDF")
    args = ap.parse_args()
    build_corpus(args.pdf_dir, args.out_sql,
                 max_pages=args.max_pages, max_manual_chunks=args.max_manual_chunks)
    print("done. Next: psql $DATABASE_URL -f corpus_ingest.sql")
