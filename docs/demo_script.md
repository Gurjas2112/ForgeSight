# ForgeSight — Demo Script (recording choreography)

Two windows: **Engineer** (frontend, localhost:3000) and **Admin/terminal** (scheduler + audit).
Backend + Ollama + Supabase/local-pg already running (see README run order). DEMO_MODE armed.

---

## 0:00 — Problem framing (Plant Overview)
Open `localhost:3000`. "Steel-plant engineers stitch answers from manuals, SOPs, logs, and
sensor alerts by hand." Point at the **6 zone tiles**, the KPI strip (availability · open alerts ·
₹ downtime-at-risk), and the **live alert feed**. The **F3 tile pulses critical** (TRIPPED ·
HSM-F3-VFD-0247); the Sinter Fan #2 tile shows an early-warning state.

## 0:30 — Scenario A: reactive diagnosis (the 90-second fix plan)
1. Click the **F3 stand** tile → Equipment Detail. Copilot greets with route context.
2. In the sidebar, click **"diagnose the F3 trip"**. Watch the **delegation stream**:
   *Orchestrator → Diagnostic Agent: searching manuals & SOPs… matching past breakdowns…*
3. A **DiagnosisCard** renders (byline *Diagnostic Agent · AI-assisted*): DC-bus overvoltage,
   **High** confidence, ranked root causes, with an **Evidence Trail** chip row.
4. **Click the `BR-2024-0312` chip** → the Evidence Drawer slides in with the *exact* verified
   breakdown record. "Every claim is cited to a real source — the guardrail makes a fabricated
   citation physically impossible."
5. Ask **"how do I check the braking resistor?"** → a **ChecklistCard** with **LOTO steps first**
   (amber, enforced by the guardrail), expected 8.0–8.4 Ω.

## 2:10 — Scenario B: proactive + governed (catch it early, commit with approval)
1. In the terminal window run `python backend/scheduler/health_scan.py --once` — the system
   **raises a CRITICAL alert** for Sinter ID Fan #2 (RUL ≈ 3 d < 21 d spare lead time). "The
   system speaks first."
2. Open the **Sinter Fan #2** detail → the **showpiece SensorTrend**: normal band, rising DE-bearing
   vibration, **molten-orange anomaly markers**, labelled 7.1 alarm line. RUL countdown + band.
3. Ask **"can it wait till Sunday?"** → the **three-agent Send fan-out** (Reliability · Planner ·
   Supervisor) → one **WaitAssessmentCard** with the verdict, margin math, monitoring plan, and the
   Planner's "lead time > RUL: reserve now" callout.
4. Ask **"go ahead and reserve the SKF 22230"** → the graph pauses at **human_gate** → an amber
   **Approval prompt**. Tap **Approve**. Say it: *"Agents propose; humans commit; everything is
   audited."*

## 3:50 — Scenario C: prioritize & prove
1. Ask **"what should we tackle first tonight?"** → a **PriorityCard** with the deterministic
   score and four weighted factor bars — "deterministic scoring, auditable."
2. Point at the **About the models** panel: anomaly recall 1.0 / 8.7 d lead, RUL RMSE 16.4 (C-MAPSS,
   by-unit split), failure recall 0.91, defect PR-AUC 0.80 — "benchmarks validate the method, the
   simulation validates the system."

## 4:40 — Trust & close
- Audit: `SELECT agent_name, action, allowed, reason FROM audit_log ORDER BY ts DESC LIMIT 10;`
  shows every allow/deny — including a denied out-of-charter attempt if staged.
- Closing line: *"Everything you just saw ran on one laptop with an open-source SLM under
  constrained decoding — fully on-premise capable, no plant data ever leaves the network. From
  fault code to fix plan in 90 seconds, auditable end to end."*

> Safety net: DEMO_MODE serves the golden F3 card instantly if Ollama stalls; for the live
> delegation-stream take, use a non-cached phrasing (e.g. "diagnose fault 0247 on the F3 stand").
