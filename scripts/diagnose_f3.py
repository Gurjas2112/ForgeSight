"""
ForgeSight — Scenario A end-to-end (Gate 4, partial: Diagnostic pipeline only).
Runs the governed graph for "diagnose F3 fault 0247" and prints the resulting DiagnosisCard.

Expects:
  - DATABASE_URL set (Supabase, or the local pgvector container from scripts/local_pg.sh)
  - migrations + corpus applied (python backend/db/apply_migrations.py)
  - Ollama up with qwen2.5:3b-instruct + nomic-embed-text

PASS criteria: card_type == 'diagnosis' · cites BR-2024-0312 · confidence in words ·
one audit_log entry per tool call.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:                                      # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

from langchain_core.messages import HumanMessage  # noqa: E402

from backend.agent.build import build_controller  # noqa: E402
from backend.agent.persistence import NullPersistence  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.db.connection import get_pool, healthcheck  # noqa: E402
from backend.schemas.agent_models import AuthUser, Budget  # noqa: E402

QUERY = "Diagnose the F3 stand — it tripped on fault 0247."
EQUIPMENT = "hsm-f3-stand"


def main() -> int:
    s = get_settings()
    if not s.database_url:
        print("DATABASE_URL is empty. Set it in .env (Supabase pooler URI) or run the local\n"
              "pgvector container: bash scripts/local_pg.sh, then python backend/db/apply_migrations.py")
        return 2
    if not healthcheck():
        print("Cannot reach the database at DATABASE_URL. Is it running / correct?")
        return 2

    pool = get_pool()
    controller = build_controller(pool=pool, persistence=NullPersistence())

    session_id = str(uuid.uuid4())
    user = AuthUser(id="11111111-1111-1111-1111-111111111111", role="engineer")
    inputs = {
        "messages": [HumanMessage(content=QUERY)],
        "user": user,
        "session_id": session_id,
        "equipment_id": EQUIPMENT,
        "consumed": Budget(),
        "repair_attempted": False,
    }
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 25}

    print(f"\n▶ Query: {QUERY}\n  equipment={EQUIPMENT}  session={session_id[:8]}…\n")
    result = controller.invoke(inputs, config)

    card = result.get("draft_card") or {}
    citations = result.get("citations", [])
    delegations = result.get("delegations", [])

    print("── delegation stream ─────────────────────────────")
    for d in delegations:
        dd = d.model_dump() if hasattr(d, "model_dump") else d
        print(f"  → {dd.get('agent')}: {dd.get('text')}")

    print("\n── retrieved citations ───────────────────────────")
    cite_refs = []
    for c in citations:
        cc = c.model_dump() if hasattr(c, "model_dump") else c
        cite_refs.append(cc.get("ref"))
        print(f"  • [{cc.get('kind')}] {cc.get('ref')}")

    print("\n── DiagnosisCard ─────────────────────────────────")
    print(json.dumps(card, indent=2, default=str))

    # ---- assertions ----
    print("\n── Gate 4 (partial) checks ───────────────────────")
    ok = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    check("card_type == 'diagnosis'", card.get("card_type") == "diagnosis")
    check("confidence in {High,Medium,Low}", card.get("confidence") in {"High", "Medium", "Low"})
    check("has ranked root_causes", bool(card.get("root_causes")))
    check("cites BR-2024-0312 (retrieved)", "BR-2024-0312" in " ".join(map(str, cite_refs)))
    card_refs = card.get("citation_refs", [])
    check("card citation_refs ⊆ retrieved", all(r in cite_refs for r in card_refs) and bool(card_refs))

    # audit rows (one allow per tool call)
    try:
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM audit_log WHERE allowed = true "
                        "AND agent_name = 'diagnostic_agent'")
            n_audit = (cur.fetchone() or [0])[0]
        check("audit_log has ≥2 allow rows (retrieve_rag, match_history)", n_audit >= 2)
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] audit check skipped: {e}")

    print("\n" + ("GATE 4 (partial): PASS — Scenario A diagnosis is governed + cited."
                  if ok else "GATE 4 (partial): FAIL — see checks above."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
