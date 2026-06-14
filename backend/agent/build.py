"""
ForgeSight — controller factory. Wires Authority + Guardrails + pipelines + SLM + caches +
persistence + checkpointer into a runnable AgentController.

`checkpointer`: MemorySaver for scripts/tests; the Postgres checkpointer (thread_id =
chat session id) in the always-on backend. `persistence`: NullPersistence for scripts,
SupabasePersistence for the API.
"""

from __future__ import annotations

from backend.agent.caches import CacheChain
from backend.agent.governance import AgentAuthority, AgentController, AgentGuardrails
from backend.agent.persistence import NullPersistence
from backend.agent.pipelines import build_sub_agents
from backend.agent.synthesis import OllamaSynthesizer
from backend.auth.audit import console_audit_sink, make_audit_sink
from backend.config import get_settings


def build_controller(pool=None, *, checkpointer=None, persistence=None,
                     audit_sink=None, demo_cache=None) -> AgentController:
    """Assemble the governed graph. Pass a psycopg pool for DB-backed tools/audit; omit for
    a pure in-memory smoke test (tools still need a pool, so scripts pass one)."""
    settings = get_settings()

    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()

    if audit_sink is None:
        audit_sink = make_audit_sink(pool) if pool is not None else console_audit_sink

    authority = AgentAuthority(audit_sink=audit_sink)
    guards = AgentGuardrails()
    sub_agents = build_sub_agents(authority, pool)
    llm = OllamaSynthesizer()
    caches = CacheChain(demo_cache=demo_cache, demo_mode=settings.demo_mode)
    persist = persistence or NullPersistence()

    return AgentController(authority=authority, guards=guards, sub_agents=sub_agents,
                           checkpointer=checkpointer, llm=llm, caches=caches,
                           persistence=persist)
