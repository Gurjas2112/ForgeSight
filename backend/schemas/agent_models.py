"""
ForgeSight — shared agent-state models + reducers. Extracted so tools, governance, synthesis,
and persistence all import ONE definition (no circular deps through governance.py).
These mirror the structured-output models in the design's agent_governance.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["manual", "sop", "history", "trend", "spares_record",
                  "priority_matrix", "model_output", "sql_query"]
    ref: str                      # e.g. "SOP-HSM-ELEC-09 §3.2", "BR-2024-0312"
    chunk_id: str | None = None   # matches doc_chunks.id and Langfuse span metadata


class DelegationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: str
    text: str
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GuardReport(BaseModel):
    passed: bool
    violations: list[str] = Field(default_factory=list)
    degraded: bool = False


class AuthUser(BaseModel):
    id: str
    role: Literal["engineer", "admin"]


class Budget(BaseModel):
    tool_calls: int = 0
    llm_calls: int = 0
    reset: bool = False     # a reset=True delta REPLACES the accumulator (turn-start), not sums


# ---- reducers (concurrent Send branches merge safely) ----

def reduce_list(left: list | None, right: list | None) -> list:
    return (left or []) + (right or [])


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


def sum_budget(left: "Budget | None", right: "Budget | None") -> "Budget":
    l, r = left or Budget(), right or Budget()
    # The budget is per-TURN. The entry node emits a reset delta so the checkpointed accumulator
    # starts each turn at zero; within a turn the parallel sub-agent branches still sum normally.
    if r.reset:
        return Budget(tool_calls=r.tool_calls, llm_calls=r.llm_calls)
    return Budget(tool_calls=l.tool_calls + r.tool_calls,
                  llm_calls=l.llm_calls + r.llm_calls)
