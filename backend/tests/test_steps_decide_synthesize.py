from __future__ import annotations

from uuid import uuid4

from kodoku.engine.steps.decide import Decision, decide
from kodoku.engine.steps.synthesize import synthesize
from kodoku.llm.fake import FakeLLMClient


def test_decide_keeps_scores_above_threshold_preserving_order() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()

    decision = decide([(a, 8.0), (b, 5.0), (c, 7.0)], depth=1, max_depth=3)

    assert decision == Decision(keep=[a, c], prune=[b], expand=[a, c])


def test_decide_keeps_highest_when_all_below_threshold() -> None:
    a, b = uuid4(), uuid4()

    decision = decide([(a, 3.0), (b, 4.0)], depth=0, max_depth=3)

    assert decision.keep == [b]
    assert decision.prune == [a]


def test_decide_expand_empty_at_max_depth() -> None:
    a, c = uuid4(), uuid4()

    decision = decide([(a, 8.0), (c, 7.0)], depth=3, max_depth=3)

    assert decision.keep == [a, c]
    assert decision.expand == []


async def test_synthesize_yields_fake_chunks_in_order() -> None:
    llm = FakeLLMClient(chunks=["Build ", "the buddy."])

    chunks = [chunk async for chunk in synthesize(llm, goal="Ship it", kept=[("A", "Do A")])]

    assert chunks == ["Build ", "the buddy."]
