"""Tests for the LLM-judge decide step and its deterministic fallback."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from kodoku.engine.steps.judge import JudgeCandidate, decide_with_judge
from kodoku.llm.fake import FakeLLMClient

pytestmark = pytest.mark.asyncio


def _cands() -> list[JudgeCandidate]:
    return [
        JudgeCandidate(id=uuid4(), title="A", content="A body", score=8.0,
                       critique="strong", dimensions={"impact": 8.0}),
        JudgeCandidate(id=uuid4(), title="B", content="B body", score=3.0,
                       critique="weak", dimensions={"impact": 3.0}),
    ]


async def test_judge_keeps_subset_and_returns_rationale() -> None:
    cands = _cands()
    keep_id, prune_id = cands[0].id, cands[1].id
    llm = FakeLLMClient(completions=[
        json.dumps({"keep": [str(keep_id)], "prune": [str(prune_id)],
                    "rationale": "A beats B"}),
    ])
    out = await decide_with_judge(llm, goal="g", candidates=cands, depth=1, max_depth=2)
    assert out.source == "judge"
    assert out.decision.keep == [keep_id]
    assert out.decision.prune == [prune_id]
    assert out.decision.expand == [keep_id]  # depth 1 < max_depth 2
    assert out.rationale == "A beats B"


async def test_judge_no_expansion_at_max_depth() -> None:
    cands = _cands()
    llm = FakeLLMClient(completions=[
        json.dumps({"keep": [str(cands[0].id)], "prune": [str(cands[1].id)],
                    "rationale": "x"}),
    ])
    out = await decide_with_judge(llm, goal="g", candidates=cands, depth=2, max_depth=2)
    assert out.decision.expand == []


async def test_falls_back_when_ids_not_exact_cover() -> None:
    cands = _cands()
    # keep references an id that isn't a candidate; prune omits a real one.
    llm = FakeLLMClient(completions=[
        json.dumps({"keep": [str(uuid4())], "prune": [], "rationale": "bad"}),
    ])
    out = await decide_with_judge(llm, goal="g", candidates=cands, depth=1, max_depth=2)
    assert out.source == "threshold_fallback"
    # threshold floor: A (8.0) >= 6.0 kept, B (3.0) pruned.
    assert out.decision.keep == [cands[0].id]
    assert out.decision.prune == [cands[1].id]
    assert out.rationale == ""


async def test_falls_back_when_keep_empty() -> None:
    cands = _cands()
    llm = FakeLLMClient(completions=[
        json.dumps({"keep": [], "prune": [str(cands[0].id), str(cands[1].id)],
                    "rationale": "prune all"}),
    ])
    out = await decide_with_judge(llm, goal="g", candidates=cands, depth=1, max_depth=2)
    assert out.source == "threshold_fallback"
    assert out.decision.keep == [cands[0].id]  # best-of by threshold floor


async def test_falls_back_when_id_in_both_keep_and_prune() -> None:
    cands = _cands()
    # B appears in both buckets — a contradictory cover. Must fall back, not
    # silently keep B by virtue of it being in `keep`.
    llm = FakeLLMClient(completions=[
        json.dumps({"keep": [str(cands[0].id), str(cands[1].id)],
                    "prune": [str(cands[1].id)], "rationale": "contradiction"}),
    ])
    out = await decide_with_judge(llm, goal="g", candidates=cands, depth=1, max_depth=2)
    assert out.source == "threshold_fallback"
    assert out.decision.keep == [cands[0].id]
    assert out.decision.prune == [cands[1].id]


async def test_falls_back_on_malformed_json() -> None:
    cands = _cands()
    # parse_json retries (retries+1 = 3 calls) then raises StepError -> fallback.
    llm = FakeLLMClient(completions=["not json", "still not", "nope"])
    out = await decide_with_judge(llm, goal="g", candidates=cands, depth=1, max_depth=2)
    assert out.source == "threshold_fallback"
    assert out.decision.keep == [cands[0].id]
