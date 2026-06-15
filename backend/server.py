"""
ForgeSight — FastAPI HTTP surface for the governed graph (the frontend talks to this).
lifespan builds the controller ONCE (DEMO_MODE cache armed); endpoints:
  POST /chat          run a turn → {card, delegations, citations, intent, ...}
  POST /chat/approve  resume a human_gate interrupt (COMMIT approval)
  GET  /equipment     · GET /equipment/{id} (+health+recent sensors) · GET /alerts · GET /healthz

Run:  uvicorn backend.server:app --port 8000   (DATABASE_URL + Ollama up)
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from psycopg.types.json import Json
from pydantic import BaseModel

from backend.agent.build import build_controller
from backend.agent.demo_cards import golden_demo_cache
from backend.auth.jwt import user_from_header
from backend.agent.persistence import SupabasePersistence
from backend.config import get_settings
from backend.db.connection import get_pool, healthcheck
from backend.schemas.agent_models import AuthUser, Budget

STATE: dict[str, Any] = {}


async def _scheduler_loop(interval: int):
    """FR-7 — background health re-scan: every `interval`s run scan_once() off the event loop
    so /alerts reflects live re-scans, not a single seed. Guarded by ENABLE_SCHEDULER."""
    import asyncio

    from backend.scheduler.health_scan import scan_once
    while True:
        try:
            await asyncio.sleep(interval)
            await asyncio.to_thread(scan_once)
        except asyncio.CancelledError:
            break
        except Exception as e:  # noqa: BLE001 — a bad scan must never kill the loop
            print(f"[scheduler] scan failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    pool = get_pool()
    STATE["pool"] = pool
    STATE["controller"] = build_controller(
        pool=pool, persistence=SupabasePersistence(pool), demo_cache=golden_demo_cache())
    s = get_settings()
    task = None
    if s.enable_scheduler:
        task = asyncio.create_task(_scheduler_loop(s.scheduler_interval_seconds))
        print(f"[scheduler] enabled · every {s.scheduler_interval_seconds}s")
    yield
    if task is not None:
        task.cancel()
    pool.close()


app = FastAPI(title="ForgeSight API", version="1.0", lifespan=lifespan)
_origins = [o.strip() for o in get_settings().allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware, allow_origins=_origins,
    allow_methods=["*"], allow_headers=["*"])


# ---------------- models ----------------

class ChatIn(BaseModel):
    message: str
    equipment_id: str | None = None
    session_id: str | None = None
    role: Literal["engineer", "admin"] = "engineer"


class ApproveIn(BaseModel):
    session_id: str
    approved: bool


class FeedbackIn(BaseModel):
    verdict: Literal["up", "down", "fixed"]
    equipment_id: str | None = None
    fault_code: str | None = None
    note: str | None = None
    session_id: str | None = None
    citation_ref: str | None = None     # the cited record a 'down' verdict demotes
    root_cause: str | None = None       # a 'fixed' verdict's confirmed root cause (→ exemplar)
    fix: str | None = None              # a 'fixed' verdict's confirmed fix (→ exemplar)


class SignupIn(BaseModel):
    email: str
    password: str
    full_name: str | None = None
    role: Literal["engineer", "admin"] = "engineer"


# ---------------- auth ----------------

def current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    """Resolve the caller from the Supabase Bearer token; demo engineer when absent/invalid."""
    return user_from_header(authorization)


# ---------------- helpers ----------------

def _serialize(result: dict) -> dict:
    def dump(x):
        return x.model_dump() if hasattr(x, "model_dump") else x
    interrupts = result.get("__interrupt__")
    pending = None
    if interrupts:
        iv = interrupts[0]
        pending = getattr(iv, "value", iv)
    return {
        "card": result.get("draft_card"),
        "delegations": [dump(d) for d in result.get("delegations", [])],
        "citations": [dump(c) for c in result.get("citations", [])],
        "intent": result.get("intent"),
        "query_class": result.get("query_class"),
        "pending_action": result.get("pending_action") or (pending or {}).get("action") if pending else result.get("pending_action"),
        "awaiting_approval": bool(interrupts),
    }


# ---------------- endpoints ----------------

@app.get("/healthz")
def healthz() -> dict:
    """Report liveness + which SLM/LLM is actually serving synthesis (proves the active backend:
    local fine-tuned Qwen via Ollama, or the Groq hosted fallback on Railway)."""
    s = get_settings()
    backend = s.synthesis_backend
    active_model = s.ollama_model if backend == "ollama" else f"{s.llm_provider}:{s.llm_model}"
    return {"ok": True, "db": healthcheck(), "synthesis_backend": backend,
            "model": active_model, "scheduler": s.enable_scheduler}


@app.post("/auth/signup")
def signup(body: SignupIn) -> dict:
    """Create a pre-confirmed Supabase user (engineer|admin) + mirror into profiles."""
    from backend.auth.supabase_admin import create_user
    try:
        u = create_user(body.email, body.password, body.role, body.full_name)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"signup failed: {e}")
    try:
        with STATE["pool"].connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO profiles (id, full_name, role) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET role = EXCLUDED.role, full_name = EXCLUDED.full_name",
                (u["id"], body.full_name or body.email.split("@")[0], body.role))
    except Exception:  # noqa: BLE001 — profile mirror is best-effort
        pass
    return {"ok": True, **u}


@app.get("/auth/me")
def me(user: AuthUser = Depends(current_user)) -> dict:
    return {"id": user.id, "role": user.role}


@app.post("/chat")
def chat(body: ChatIn, user: AuthUser = Depends(current_user)) -> dict:
    controller = STATE["controller"]
    session_id = body.session_id or str(uuid.uuid4())
    inputs = {
        "messages": [HumanMessage(content=body.message)],
        "user": user,
        "session_id": session_id,
        "equipment_id": body.equipment_id,
        "consumed": Budget(),
        "repair_attempted": False,
    }
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 25}
    result = controller.invoke(inputs, config)
    out = _serialize(result)
    out["session_id"] = session_id
    return out


@app.post("/chat/approve")
def approve(body: ApproveIn) -> dict:
    """Resume a paused human_gate with the engineer's decision (agents propose; humans commit)."""
    controller = STATE["controller"]
    config = {"configurable": {"thread_id": body.session_id}, "recursion_limit": 25}
    try:
        result = controller.graph.invoke(Command(resume={"approved": body.approved}), config)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"no resumable turn for that session: {e}")
    out = _serialize(result)
    out["session_id"] = body.session_id
    out["approved"] = body.approved
    return out


@app.get("/equipment")
def equipment() -> list[dict]:
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT e.id, e.name, e.zone, e.criticality, h.anomaly_score, h.is_anomalous, "
                    "h.rul_days FROM equipment e LEFT JOIN equipment_health h ON h.equipment_id=e.id "
                    "ORDER BY e.criticality DESC")
        rows = cur.fetchall()
    return [{"id": r[0], "name": r[1], "zone": r[2], "criticality": r[3],
             "anomaly_score": r[4], "is_anomalous": r[5], "rul_days": r[6]} for r in rows]


@app.get("/equipment/{eq_id}")
def equipment_detail(eq_id: str) -> dict:
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name, zone, criticality, thresholds FROM equipment WHERE id=%s", (eq_id,))
        e = cur.fetchone()
        if not e:
            raise HTTPException(404, "unknown equipment")
        cur.execute("SELECT anomaly_score, is_anomalous, rul_days, rul_band, contributing_sensors "
                    "FROM equipment_health WHERE equipment_id=%s", (eq_id,))
        h = cur.fetchone()
        cur.execute("SELECT ts, vibration_de, bearing_temp FROM sensor_readings WHERE equipment_id=%s "
                    "ORDER BY ts DESC LIMIT 288", (eq_id,))
        sensors = [{"ts": str(r[0]), "vibration_de": float(r[1]), "bearing_temp": float(r[2])}
                   for r in reversed(cur.fetchall())]
    return {
        "id": e[0], "name": e[1], "zone": e[2], "criticality": e[3], "thresholds": e[4],
        "health": ({"anomaly_score": h[0], "is_anomalous": h[1], "rul_days": h[2],
                    "rul_band": h[3], "contributing_sensors": h[4]} if h else None),
        "sensors": sensors,
    }


@app.get("/evidence")
def evidence(ref: str) -> dict:
    """Resolve a citation ref to its exact source excerpt (Evidence Drawer). doc_chunks for
    manuals/SOPs/records; a description for trend/matrix/model citations."""
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT content, doc_type, source, section_ref FROM doc_chunks "
                    "WHERE section_ref = %s OR section_ref = %s OR section_ref ILIKE %s LIMIT 1",
                    (ref, ref + " [VERIFIED]", f"%{ref}%"))
        r = cur.fetchone()
    if r:
        return {"ref": ref, "kind": r[1], "source": r[2], "section_ref": r[3], "content": r[0]}
    return {"ref": ref, "kind": "derived", "source": "ForgeSight",
            "content": f"{ref} — derived from a deterministic tool / ML model output "
                       "(priority matrix, vibration trend, or anomaly scan). Not a document."}


@app.post("/feedback")
def feedback(body: FeedbackIn) -> dict:
    """FR-6 — feedback-driven improvement. Capture up/down/fixed; a 'fixed' verdict flips the
    matching breakdown record to engineer-verified (earns the green chip) and logs it. Agent
    suggestions and confirmed facts are never conflated — only human-verified records turn green."""
    # FR-6 — condition future retrieval/synthesis on this verdict (demonstrably changes answers)
    from backend.tools import feedback_store
    feedback_store.record(body.verdict, equipment_id=body.equipment_id, fault_code=body.fault_code,
                          citation_ref=body.citation_ref, root_cause=body.root_cause, fix=body.fix)

    verified_ref = None
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO feedback (verdict, note, equipment_id) VALUES (%s, %s, %s) RETURNING id",
            (body.verdict, body.note, body.equipment_id))
        fid = cur.fetchone()[0]
        if body.verdict == "fixed" and body.equipment_id:
            # flip the matching (or most recent) breakdown record for this equipment to verified
            cur.execute(
                "UPDATE breakdown_history SET verified = true "
                "WHERE id = (SELECT id FROM breakdown_history WHERE equipment_id = %s "
                "  AND (%s::text IS NULL OR fault_code = %s) ORDER BY occurred_at DESC LIMIT 1) "
                "RETURNING id", (body.equipment_id, body.fault_code, body.fault_code))
            row = cur.fetchone()
            verified_ref = row[0] if row else None
            cur.execute(
                "INSERT INTO logbook (equipment_id, author_type, entry_type, content) "
                "VALUES (%s, 'human', 'fix_confirmed', %s)",
                (body.equipment_id, Json({"note": body.note, "fault_code": body.fault_code,
                                          "verified_record": verified_ref})))
    return {"ok": True, "feedback_id": str(fid), "verified_record": verified_ref}


@app.get("/models/scorecard")
def models_scorecard() -> dict:
    """About-the-models panel: each model's training metrics + a LIVE held-out inference
    (defect via LightGBM; failure/azure/RUL via XGBoost). Every advertised number is a real,
    reproducible model output, not a static claim."""
    from backend.tools.ml_tools import model_scorecard
    try:
        return model_scorecard()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"scorecard unavailable (models not published?): {e}")


@app.get("/alerts")
def alerts() -> list[dict]:
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, equipment_id, severity, title, created_at FROM alerts "
                    "ORDER BY created_at DESC LIMIT 20")
        return [{"id": str(r[0]), "equipment_id": r[1], "severity": r[2], "title": r[3],
                 "created_at": str(r[4])} for r in cur.fetchall()]


# ---------------- §5.4 reports (ReportLab PDF) ----------------

@app.get("/reports/alert")
def report_alert(equipment_id: str) -> Response:
    """Abnormal-alert PDF report for one equipment (health + open alerts + related history)."""
    from backend.tools.reports import generate_alert_report
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name, zone, criticality FROM equipment WHERE id=%s", (equipment_id,))
        e = cur.fetchone()
        if not e:
            raise HTTPException(404, "unknown equipment")
        equipment = {"id": e[0], "name": e[1], "zone": e[2], "criticality": e[3]}
        cur.execute("SELECT anomaly_score, is_anomalous, rul_days, contributing_sensors "
                    "FROM equipment_health WHERE equipment_id=%s", (equipment_id,))
        hr = cur.fetchone()
        health = ({"anomaly_score": hr[0], "is_anomalous": hr[1], "rul_days": hr[2],
                   "contributing_sensors": hr[3]} if hr else None)
        cur.execute("SELECT severity, title, created_at FROM alerts WHERE equipment_id=%s "
                    "ORDER BY created_at DESC LIMIT 12", (equipment_id,))
        al = [{"severity": r[0], "title": r[1], "created_at": r[2]} for r in cur.fetchall()]
        cur.execute("SELECT id, occurred_at, fault_code, root_cause, verified FROM breakdown_history "
                    "WHERE equipment_id=%s ORDER BY occurred_at DESC LIMIT 5", (equipment_id,))
        bd = [{"id": r[0], "occurred_at": str(r[1]), "fault_code": r[2], "root_cause": r[3],
               "verified": r[4]} for r in cur.fetchall()]
    pdf = generate_alert_report(equipment=equipment, health=health, alerts=al, breakdowns=bd)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="alert_{equipment_id}.pdf"'})


@app.get("/reports/shift-summary")
def report_shift() -> Response:
    """Plant-wide shift summary PDF (open alerts across the plant)."""
    from backend.tools.reports import draft_shift_summary
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT severity, equipment_id, title FROM alerts ORDER BY created_at DESC LIMIT 15")
        al = [{"severity": r[0], "equipment_id": r[1], "title": r[2]} for r in cur.fetchall()]
    pdf = draft_shift_summary(alerts=al)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="shift_summary.pdf"'})
