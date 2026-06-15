"""Per-turn budget must reset between turns. The `consumed` accumulator is checkpointed across
turns in a session; without a turn-start reset the tool-budget cap accumulates and later turns get
spuriously denied ('exceeded per-turn tool budget'). Pure reducer tests."""

from __future__ import annotations

from backend.schemas.agent_models import Budget, sum_budget


def test_normal_sum_accumulates_within_a_turn():
    # parallel sub-agent branches in one turn still sum
    assert sum_budget(Budget(tool_calls=2), Budget(tool_calls=3)).tool_calls == 5
    assert sum_budget(Budget(llm_calls=1), Budget(llm_calls=2)).llm_calls == 3


def test_reset_delta_replaces_the_accumulator():
    # the entry node emits Budget(reset=True) at turn start → accumulator goes back to zero
    after = sum_budget(Budget(tool_calls=6, llm_calls=4), Budget(reset=True))
    assert after.tool_calls == 0 and after.llm_calls == 0


def test_turn_sequence_does_not_leak_across_turns():
    # simulate: turn 1 spends 2, reset, turn 2 spends 2 → still well under the cap of 6
    consumed = Budget()
    for _ in range(5):                       # five diagnosis turns in one session
        consumed = sum_budget(consumed, Budget(reset=True))   # ingest_and_authorize
        consumed = sum_budget(consumed, Budget(tool_calls=2))  # diagnostic pipeline delta
        assert consumed.tool_calls == 2      # never climbs past a single turn's spend
