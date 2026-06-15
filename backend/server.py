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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel

from backend.agent.build import build_controller
from backend.agent.demo_cards import golden_demo_cache
from backend.agent.persistence import SupabasePersistence
from backend.config import get_settings
from backend.db.connection import get_pool, healthcheck
from backend.schemas.agent_models import AuthUser, Budget

STATE: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = get_pool()
    STATE["pool"] = pool
    STATE["controller"] = build_controller(
        pool=pool, persistence=SupabasePersistence(pool), demo_cache=golden_demo_cache())
    yield
    pool.close()


app = FastAPI(title="ForgeSight API", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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
    return {"ok": True, "db": healthcheck(), "model": get_settings().ollama_model}


@app.post("/chat")
def chat(body: ChatIn) -> dict:
    controller = STATE["controller"]
    session_id = body.session_id or str(uuid.uuid4())
    inputs = {
        "messages": [HumanMessage(content=body.message)],
        "user": AuthUser(id="11111111-1111-1111-1111-111111111111", role=body.role),
        "session_id": session_id,
        "equipment_id": body.equipment_id,
        "consumed": Budget(),
        "repair_attempted": False,
    }
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 25}
    result = controller.graph.invoke(inputs, config)
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


@app.get("/alerts")
def alerts() -> list[dict]:
    with STATE["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, equipment_id, severity, title, created_at FROM alerts "
                    "ORDER BY created_at DESC LIMIT 20")
        return [{"id": str(r[0]), "equipment_id": r[1], "severity": r[2], "title": r[3],
                 "created_at": str(r[4])} for r in cur.fetchall()]
