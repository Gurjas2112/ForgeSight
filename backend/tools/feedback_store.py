"""
ForgeSight — feedback-conditioned retrieval store (FR-6).
=========================================================
Makes /feedback DEMONSTRABLY change future answers without retraining weights (honest framing:
feedback-conditioned retrieval + few-shot exemplar injection):

  - verdict "down"  → penalises the cited record for that (equipment, fault_code): match_history
                      demotes it on the next ask, so a different root cause floats up.
  - verdict "fixed" → records the engineer-confirmed root cause / fix as a VERIFIED exemplar for
                      that (equipment, fault_code); synthesis injects it as a few-shot so the next
                      diagnosis leads with the confirmed cause.

Process-global (one warm backend process serves the demo); /feedback also persists every verdict
to the DB `feedback` table for durability/audit. This is retrieval/exemplar conditioning, NOT
model retraining — stated plainly in the docs.
"""

from __future__ import annotations

from threading import Lock

_LOCK = Lock()
# (equipment_id, FAULT) -> count of down-votes  (group-level penalty)
_PENALTIES: dict[tuple[str, str], int] = {}
# (equipment_id, FAULT) -> set of explicitly down-voted citation refs
_DEMOTED: dict[tuple[str, str], set[str]] = {}
# (equipment_id, FAULT) -> list of {root_cause, fix} engineer-confirmed exemplars
_EXEMPLARS: dict[tuple[str, str], list[dict]] = {}


def _key(equipment_id: str | None, fault_code: str | None) -> tuple[str, str]:
    return (equipment_id or "", (fault_code or "").upper())


def record(verdict: str, *, equipment_id: str | None, fault_code: str | None,
           citation_ref: str | None = None, root_cause: str | None = None,
           fix: str | None = None) -> None:
    """Apply a feedback verdict to the in-process conditioning store."""
    k = _key(equipment_id, fault_code)
    with _LOCK:
        if verdict == "down":
            _PENALTIES[k] = _PENALTIES.get(k, 0) + 1
            if citation_ref:
                _DEMOTED.setdefault(k, set()).add(citation_ref.replace(" [VERIFIED]", ""))
        elif verdict == "fixed":
            if root_cause or fix:
                _EXEMPLARS.setdefault(k, []).append(
                    {"root_cause": root_cause or "", "fix": fix or ""})


def penalty_for(equipment_id: str | None, fault_code: str | None) -> int:
    return _PENALTIES.get(_key(equipment_id, fault_code), 0)


def demoted_refs(equipment_id: str | None, fault_code: str | None) -> set[str]:
    return set(_DEMOTED.get(_key(equipment_id, fault_code), set()))


def exemplars_for(equipment_id: str | None, fault_code: str | None) -> list[dict]:
    return list(_EXEMPLARS.get(_key(equipment_id, fault_code), []))


def reset() -> None:
    """Test hook — clear all conditioning."""
    with _LOCK:
        _PENALTIES.clear()
        _DEMOTED.clear()
        _EXEMPLARS.clear()
