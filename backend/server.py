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
from pydantic import BaseModel, EmailStr, field_validator

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
    email: EmailStr                       # RFC-validated server-side (422 on malformed input)
    password: str
    full_name: str | None = None
    role: Literal["engineer", "admin"] = "engineer"

    @field_validator("password")
    @classmethod
    def _strong_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("password must contain at least one letter and one number")
        return v


class WorkOrderIn(BaseModel):
    equipment_id: str
    title: str
    description: str | None = None
    alert_id: str | None = None
    session_id: str | None = None
    priority: int = 50
    steps: list[dict] | None = None


class WorkOrderPatch(BaseModel):
    status: Literal["draft", "open", "in_progress", "completed", "cancelled"] | None = None
    steps: list[dict] | None = None
    priority: int | None = None


class HandoverIn(BaseModel):
    equipment_id: str
    notes: str
    open_work_orders: list[str] | None = None
    risk_context: dict | None = None


# ---------------- auth ----------------

def current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    """Resolve the caller from the Supabase Bearer token; demo engineer when absent/invalid."""
    return user_from_header(authorization)


def require_admin(user: AuthUser = Depends(current_user)) -> AuthUser:
    """Gate a route to authenticated admins (agents propose; only admins provision)."""
    if user.role != "admin":
        raise HTTPException(403, "admin only")
    return user


def _audit_signup_downgrade(email: str) -> None:
    """Record a denied self-assign-admin signup attempt (best-effort, never breaks the request)."""
    try:
        with STATE["pool"].connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_log (agent_name, action, resource, allowed, reason, detail) "
                "VALUES ('auth', 'signup_admin', 'auth.users', false, "
                "'public signup may not self-assign admin; downgraded to engineer', %s::jsonb)",
                (Json({"email": email}),))
    except Exception:  # noqa: BLE001
        pass


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
def signup(body: SignupIn, authorization: str | None = Header(default=None)) -> dict:
    """Create a pre-confirmed Supabase user + mirror into profiles.

    Public signup is **engineer-only**. Creating an admin requires an authenticated admin caller
    (Bearer token) — this closes the self-assign-admin hole; the route, not just the GoTrue helper,
    now enforces authorization. Seeded `admin@demo.forgesight` remains the reliable admin path.
    """
    from backend.auth.supabase_admin import DuplicateUserError, create_user
    role = body.role
    if role == "admin" and user_from_header(authorization).role != "admin":
        role = "engineer"  # downgrade unauthorized admin requests rather than 500
        _audit_signup_downgrade(body.email)
    try:
        u = create_user(str(body.email), body.password, role, body.full_name)
    except DuplicateUserError:
        raise HTTPException(409, "An account with this email already exists. Try logging in.")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"signup failed: {e}")
    try:
        with STATE["pool"].connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO profiles (id, full_name, role) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET role = EXCLUDED.role, full_name = EXCLUDED.full_name",
                (u["id"], body.full_name or body.email.split("@")[0], role))
    except Exception:  # noqa: BLE001 — profile mirror is best-effort
        pass
    return {"ok": True, **u}


@app.get("/auth/me")
def me(user: AuthUser = Depends(current_user)) -> dict:
    return {"id": user.id, "role": user.role}


def _ensure_session(session_id: str, user: AuthUser, equipment_id: str | None, message: str) -> None:
    """Create the chat_sessions row on first turn (so chat_messages' FK is satisfied) and log the
    user's message. Without this the persistence egress silently fails the FK and no history is
    stored. Best-effort: a DB hiccup must never break the turn."""
    title = (message or "").strip()[:60] or "New conversation"
    try:
        with STATE["pool"].connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_sessions (id, user_id, equipment_id, title) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET updated_at = now()",
                (session_id, user.id, equipment_id, title))
            cur.execute(
                "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, 'user', %s)",
                (session_id, message))
    except Exception as e:  # noqa: BLE001
        print(f"  [persist] ensure_session failed (non-fatal): {e}")


@app.post("/chat")
def chat(body: ChatIn, user: AuthUser = Depends(current_user)) -> dict:
    controller = STATE["controller"]
    session_id = body.session_id or str(uuid.uuid4())
    _ensure_session(session_id, user, body.equipment_id, body.message)
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


@app.get("/chat/sessions")
def chat_sessions(user: AuthUser = Depends(current_user)) -> list[dict]:
    """List the caller's conversations (admins see all) for the copilot history switcher."""
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        base = ("SELECT s.id, s.title, s.equipment_id, s.updated_at, count(m.id) "
                "FROM chat_sessions s LEFT JOIN chat_messages m ON m.session_id = s.id ")
        if user.role == "admin":
            cur.execute(base + "GROUP BY s.id ORDER BY s.updated_at DESC LIMIT 50")
        else:
            cur.execute(base + "WHERE s.user_id = %s GROUP BY s.id "
                        "ORDER BY s.updated_at DESC LIMIT 50", (user.id,))
        return [{"id": str(r[0]), "title": r[1], "equipment_id": r[2],
                 "updated_at": str(r[3]), "message_count": int(r[4])} for r in cur.fetchall()]


@app.get("/chat/sessions/{session_id}/messages")
def chat_session_messages(session_id: str, user: AuthUser = Depends(current_user)) -> list[dict]:
    """Return a conversation's ordered messages (with timestamps) so the UI can restore it.
    Only the owner — or an admin — may read a session."""
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM chat_sessions WHERE id = %s", (session_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(404, "session not found")
        if user.role != "admin" and str(row[0]) != str(user.id):
            raise HTTPException(403, "not your session")
        cur.execute(
            "SELECT role, content, card_json, agent_name, created_at FROM chat_messages "
            "WHERE session_id = %s ORDER BY created_at", (session_id,))
        return [{"role": r[0], "content": r[1], "card": r[2], "agent_name": r[3],
                 "created_at": str(r[4])} for r in cur.fetchall()]


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


@app.get("/plant/summary")
def plant_summary() -> dict:
    """Plant KPI header: criticality-weighted availability, open-alert count, and a
    downtime-at-risk estimate — all computed deterministically from live plant state (no
    hardcoded numbers). The cost model is a documented assumption (see the `assumptions` field)."""
    from backend.tools.plant_summary import compute_plant_summary
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT e.id, e.criticality, h.is_anomalous, h.rul_days "
                    "FROM equipment e LEFT JOIN equipment_health h ON h.equipment_id=e.id")
        eq = [{"id": r[0], "criticality": r[1], "is_anomalous": r[2], "rul_days": r[3]}
              for r in cur.fetchall()]
        cur.execute("SELECT equipment_id, total_downtime_hrs, breakdowns FROM v_downtime_by_equipment")
        dt = [{"equipment_id": r[0], "total_downtime_hrs": r[1], "breakdowns": r[2]}
              for r in cur.fetchall()]
        # one row per alerting asset (highest open severity) — the scheduler re-inserts each scan,
        # so a raw row count is noise; distinct alerting equipment is the meaningful headline.
        cur.execute("SELECT equipment_id, max(severity) FROM alerts WHERE acked_at IS NULL "
                    "GROUP BY equipment_id")
        al = [{"equipment_id": r[0], "severity": r[1]} for r in cur.fetchall()]
    return compute_plant_summary(eq, dt, al)


# ---------------- admin (system metrics) ----------------

@app.get("/admin/metrics")
def admin_metrics(_: AuthUser = Depends(require_admin)) -> dict:
    """Admin-only system scorecard — every value is a live aggregate over the operational DB
    (accounts, knowledge corpus, conversations, feedback, work orders, governance audit) plus
    the deterministic plant KPI header. No hardcoded numbers."""
    from backend.tools.plant_summary import compute_plant_summary
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        def scalar(sql: str, params: tuple = ()) -> int:
            cur.execute(sql, params)
            r = cur.fetchone()
            return int(r[0]) if r and r[0] is not None else 0

        cur.execute("SELECT role, count(*) FROM profiles GROUP BY role")
        accounts_by_role = {r[0]: int(r[1]) for r in cur.fetchall()}
        cur.execute("SELECT status, count(*) FROM work_orders GROUP BY status")
        work_orders_by_status = {r[0]: int(r[1]) for r in cur.fetchall()}
        cur.execute("SELECT verdict, count(*) FROM feedback GROUP BY verdict")
        feedback_by_verdict = {r[0]: int(r[1]) for r in cur.fetchall()}

        metrics = {
            "accounts": {
                "total": sum(accounts_by_role.values()),
                "by_role": accounts_by_role,
            },
            "knowledge": {
                "equipment": scalar("SELECT count(*) FROM equipment"),
                "doc_chunks": scalar("SELECT count(*) FROM doc_chunks"),
                "spares": scalar("SELECT count(*) FROM spares"),
                "breakdown_records": scalar("SELECT count(*) FROM breakdown_history"),
            },
            "conversations": {
                "sessions": scalar("SELECT count(*) FROM chat_sessions"),
                "messages": scalar("SELECT count(*) FROM chat_messages"),
                "active_24h": scalar(
                    "SELECT count(*) FROM chat_sessions WHERE updated_at > now() - interval '24 hours'"),
            },
            "feedback": {
                "total": sum(feedback_by_verdict.values()),
                "by_verdict": feedback_by_verdict,
            },
            "work_orders": {
                "total": sum(work_orders_by_status.values()),
                "by_status": work_orders_by_status,
            },
            "governance": {
                "audit_events_total": scalar("SELECT count(*) FROM audit_log"),
                "audit_events_24h": scalar(
                    "SELECT count(*) FROM audit_log WHERE ts > now() - interval '24 hours'"),
                "denied_24h": scalar(
                    "SELECT count(*) FROM audit_log WHERE allowed = false "
                    "AND ts > now() - interval '24 hours'"),
            },
            "alerts": {
                "open": scalar("SELECT count(*) FROM alerts WHERE acked_at IS NULL"),
            },
        }

        # deterministic plant KPI header (reuses /plant/summary's compute path)
        cur.execute("SELECT e.id, e.criticality, h.is_anomalous, h.rul_days "
                    "FROM equipment e LEFT JOIN equipment_health h ON h.equipment_id=e.id")
        eq = [{"id": r[0], "criticality": r[1], "is_anomalous": r[2], "rul_days": r[3]}
              for r in cur.fetchall()]
        cur.execute("SELECT equipment_id, total_downtime_hrs, breakdowns FROM v_downtime_by_equipment")
        dt = [{"equipment_id": r[0], "total_downtime_hrs": r[1], "breakdowns": r[2]}
              for r in cur.fetchall()]
        cur.execute("SELECT equipment_id, max(severity) FROM alerts WHERE acked_at IS NULL "
                    "GROUP BY equipment_id")
        al = [{"equipment_id": r[0], "severity": r[1]} for r in cur.fetchall()]
    metrics["plant"] = compute_plant_summary(eq, dt, al)
    return metrics


@app.get("/admin/users")
def admin_users(_: AuthUser = Depends(require_admin)) -> list[dict]:
    """Admin-only account roster (from `profiles`)."""
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, full_name, role, area FROM profiles ORDER BY role, full_name")
        return [{"id": str(r[0]), "full_name": r[1], "role": r[2], "area": r[3]}
                for r in cur.fetchall()]


@app.get("/admin/audit")
def admin_audit(limit: int = 50, _: AuthUser = Depends(require_admin)) -> list[dict]:
    """Admin-only recent governance audit trail (allow/deny decisions)."""
    limit = max(1, min(limit, 200))
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT agent_name, action, resource, allowed, reason, ts "
                    "FROM audit_log ORDER BY ts DESC LIMIT %s", (limit,))
        return [{"agent_name": r[0], "action": r[1], "resource": r[2], "allowed": r[3],
                 "reason": r[4], "ts": str(r[5])} for r in cur.fetchall()]


# ---------------- dashboard modules ----------------

@app.get("/search")
def search(q: str = "", types: str = "", equipment_id: str | None = None, limit: int = 30,
           user: AuthUser = Depends(current_user)) -> dict:
    from backend.tools.search import unified_search
    type_list = [t.strip() for t in types.split(",") if t.strip()] or None
    with STATE["pool"].connection() as conn:
        items = unified_search(conn, q=q, types=type_list, equipment_id=equipment_id, limit=limit)
    return {"items": items, "count": len(items)}


@app.get("/work-orders")
def work_orders_list(equipment_id: str | None = None, status: str | None = None,
                     user: AuthUser = Depends(current_user)) -> list[dict]:
    from backend.tools.work_orders import list_work_orders
    with STATE["pool"].connection() as conn:
        return list_work_orders(conn, equipment_id=equipment_id, status=status)


@app.get("/work-orders/{wo_id}")
def work_order_get(wo_id: str, user: AuthUser = Depends(current_user)) -> dict:
    from backend.tools.work_orders import get_work_order
    with STATE["pool"].connection() as conn:
        wo = get_work_order(conn, wo_id)
    if not wo:
        raise HTTPException(404, "work order not found")
    return wo


@app.post("/work-orders")
def work_order_create(body: WorkOrderIn, user: AuthUser = Depends(current_user)) -> dict:
    from backend.tools.work_orders import create_work_order
    with STATE["pool"].connection() as conn:
        return create_work_order(conn, equipment_id=body.equipment_id, title=body.title,
                                 description=body.description, alert_id=body.alert_id,
                                 session_id=body.session_id, priority=body.priority, steps=body.steps)


@app.patch("/work-orders/{wo_id}")
def work_order_patch(wo_id: str, body: WorkOrderPatch, user: AuthUser = Depends(current_user)) -> dict:
    from backend.tools.work_orders import update_work_order
    with STATE["pool"].connection() as conn:
        wo = update_work_order(conn, wo_id, status=body.status, steps=body.steps, priority=body.priority)
    if not wo:
        raise HTTPException(404, "work order not found")
    return wo


@app.get("/work-orders/{wo_id}/export")
def work_order_export(wo_id: str, format: str = "json", user: AuthUser = Depends(current_user)) -> Response:
    from backend.tools.work_orders import export_work_order
    try:
        with STATE["pool"].connection() as conn:
            body, mime, fname = export_work_order(conn, wo_id, format)
    except ValueError:
        raise HTTPException(404, "work order not found")
    return Response(body, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.get("/incidents")
def incidents_list(equipment_id: str | None = None, user: AuthUser = Depends(current_user)) -> list[dict]:
    from backend.tools.incidents import list_incidents
    with STATE["pool"].connection() as conn:
        return list_incidents(conn, equipment_id=equipment_id)


@app.get("/incidents/{incident_id}")
def incident_get(incident_id: str, user: AuthUser = Depends(current_user)) -> dict:
    from backend.tools.incidents import get_incident
    with STATE["pool"].connection() as conn:
        inc = get_incident(conn, incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    return inc


@app.get("/incidents/{incident_id}/replay")
def incident_replay(incident_id: str, user: AuthUser = Depends(current_user)) -> dict:
    from backend.tools.incidents import incident_replay as replay
    with STATE["pool"].connection() as conn:
        data = replay(conn, incident_id)
    if not data:
        raise HTTPException(404, "incident not found")
    return data


@app.get("/incidents/{incident_id}/lessons")
def incident_lessons(incident_id: str, user: AuthUser = Depends(current_user)) -> dict:
    from backend.tools.incidents import incident_lessons as lessons
    with STATE["pool"].connection() as conn:
        return lessons(conn, incident_id)


@app.get("/spares")
def spares_catalog(equipment_id: str | None = None, low_stock: bool = False,
                   user: AuthUser = Depends(current_user)) -> list[dict]:
    from backend.tools.inventory_optimizer import list_spares_catalog
    with STATE["pool"].connection() as conn:
        return list_spares_catalog(conn, equipment_id=equipment_id, low_stock=low_stock)


@app.get("/inventory/optimizer")
def inventory_optimizer(user: AuthUser = Depends(current_user)) -> dict:
    from backend.tools.inventory_optimizer import compute_optimizer
    with STATE["pool"].connection() as conn:
        return compute_optimizer(conn)


@app.get("/reliability/plant")
def reliability_plant(user: AuthUser = Depends(current_user)) -> dict:
    from backend.tools.reliability_analytics import reliability_plant as plant
    with STATE["pool"].connection() as conn:
        return plant(conn)


@app.get("/reliability/{eq_id}")
def reliability_equipment(eq_id: str, user: AuthUser = Depends(current_user)) -> dict:
    from backend.tools.reliability_analytics import reliability_for_equipment
    with STATE["pool"].connection() as conn:
        data = reliability_for_equipment(conn, eq_id)
    if not data:
        raise HTTPException(404, "unknown equipment")
    return data


@app.get("/leadership/roi")
def leadership_roi(user: AuthUser = Depends(current_user)) -> dict:
    from backend.tools.leadership_roi import compute_leadership_roi
    with STATE["pool"].connection() as conn:
        return compute_leadership_roi(conn)


@app.get("/equipment/{eq_id}/context")
def equipment_context(eq_id: str, user: AuthUser = Depends(current_user)) -> dict:
    """Composite live risk context for the operational console."""
    from backend.tools.inventory_optimizer import list_spares_catalog
    from backend.tools.leadership_roi import _inr
    from backend.tools.plant_summary import BASE_INR_PER_HR, DEFAULT_DOWNTIME_HRS
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT e.id, e.name, e.zone, e.criticality, h.anomaly_score, h.is_anomalous, "
            "h.rul_days, h.contributing_sensors FROM equipment e "
            "LEFT JOIN equipment_health h ON h.equipment_id = e.id WHERE e.id = %s", (eq_id,))
        e = cur.fetchone()
        if not e:
            raise HTTPException(404, "unknown equipment")
        cur.execute("SELECT id, severity, title FROM alerts WHERE equipment_id = %s AND acked_at IS NULL "
                    "ORDER BY created_at DESC LIMIT 5", (eq_id,))
        alerts = [{"id": str(r[0]), "severity": r[1], "title": r[2]} for r in cur.fetchall()]
        cur.execute("SELECT id, title, status, priority FROM work_orders WHERE equipment_id = %s "
                    "AND status NOT IN ('completed','cancelled') ORDER BY priority DESC LIMIT 5", (eq_id,))
        wos = [{"id": str(r[0]), "title": r[1], "status": r[2], "priority": r[3]} for r in cur.fetchall()]
        cur.execute("SELECT total_downtime_hrs, breakdowns FROM v_downtime_by_equipment WHERE equipment_id = %s",
                    (eq_id,))
        dt = cur.fetchone()
        avg_hrs = DEFAULT_DOWNTIME_HRS
        if dt and dt[1]:
            avg_hrs = float(dt[0] or 0) / max(int(dt[1]), 1)
        spares = list_spares_catalog(conn, equipment_id=eq_id)
    at_risk = bool(e[5]) and (e[6] is not None and float(e[6]) < 14)
    failure_cost = avg_hrs * BASE_INR_PER_HR * float(e[3] or 1) if at_risk else 0
    return {
        "equipment_id": e[0], "name": e[1], "zone": e[2], "criticality": e[3],
        "anomaly_score": e[4], "is_anomalous": e[5], "rul_days": e[6],
        "contributing_sensors": e[7] or [],
        "open_alerts": alerts, "open_work_orders": wos, "spares": spares[:3],
        "downtime_at_risk_inr": round(failure_cost),
        "downtime_at_risk_label": _inr(failure_cost) if failure_cost else "—",
    }


@app.get("/maintenance/logbook")
def maintenance_logbook(equipment_id: str | None = None, user: AuthUser = Depends(current_user)) -> list[dict]:
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        if equipment_id:
            cur.execute("SELECT id, equipment_id, author_type, entry_type, content, created_at "
                        "FROM logbook WHERE equipment_id = %s ORDER BY created_at DESC LIMIT 30",
                        (equipment_id,))
        else:
            cur.execute("SELECT id, equipment_id, author_type, entry_type, content, created_at "
                        "FROM logbook ORDER BY created_at DESC LIMIT 30")
        return [{"id": str(r[0]), "equipment_id": r[1], "author_type": r[2], "entry_type": r[3],
                 "content": r[4], "created_at": str(r[5])} for r in cur.fetchall()]


@app.post("/maintenance/handover")
def maintenance_handover(body: HandoverIn, user: AuthUser = Depends(current_user)) -> dict:
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO logbook (equipment_id, author_type, author_id, entry_type, content) "
            "VALUES (%s, 'human', %s, 'shift_handover', %s) RETURNING id",
            (body.equipment_id, user.id, Json({
                "notes": body.notes,
                "open_work_orders": body.open_work_orders or [],
                "risk_context": body.risk_context or {},
            })))
        lid = cur.fetchone()[0]
    return {"ok": True, "logbook_id": str(lid)}


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
