from __future__ import annotations

import pytest

from kodoku.engine.steps.evaluate import EvaluationResult, evaluate
from kodoku.engine.steps.expand import Candidate, ExpandResult, expand
from kodoku.engine.steps.parse import StepError, parse_json
from kodoku.llm.fake import FakeLLMClient


async def test_expand_returns_candidates_from_fake_reply() -> None:
    llm = FakeLLMClient.from_json(
        [
            {
                "candidates": [
                    {"title": "A", "content": "Do A"},
                    {"title": "B", "content": "Do B"},
                    {"title": "C", "content": "Do C"},
                ]
            }
        ]
    )

    candidates = await expand(
        llm,
        goal="Ship the feature",
        parent_title="Root",
        parent_content="Start here",
        branching_factor=3,
    )

    assert candidates == [
        Candidate(title="A", content="Do A"),
        Candidate(title="B", content="Do B"),
        Candidate(title="C", content="Do C"),
    ]


async def test_expand_truncates_over_long_candidate_list() -> None:
    llm = FakeLLMClient.from_json(
        [
            {
                "candidates": [
                    {"title": "A", "content": "Do A"},
                    {"title": "B", "content": "Do B"},
                    {"title": "C", "content": "Do C"},
                    {"title": "D", "content": "Do D"},
                ]
            }
        ]
    )

    candidates = await expand(
        llm,
        goal="Ship the feature",
        parent_title="Root",
        parent_content="Start here",
        branching_factor=2,
    )

    assert [c.title for c in candidates] == ["A", "B"]


async def test_expand_accepts_short_candidate_list_without_padding() -> None:
    llm = FakeLLMClient.from_json(
        [{"candidates": [{"title": "A", "content": "Do A"}]}]
    )

    candidates = await expand(
        llm,
        goal="Ship the feature",
        parent_title="Root",
        parent_content="Start here",
        branching_factor=3,
    )

    assert len(candidates) == 1


async def test_evaluate_returns_parsed_score_critique_dimensions() -> None:
    llm = FakeLLMClient.from_json(
        [
            {
                "score": 7.5,
                "critique": "Solid but risky.",
                "dimensions": {
                    "feasibility": 8,
                    "novelty": 6,
                    "impact": 7,
                    "effort": 5,
                    "fit": 9,
                },
            }
        ]
    )

    result = await evaluate(
        llm,
        goal="Ship the feature",
        candidate_title="A",
        candidate_content="Do A",
    )

    assert result == EvaluationResult(
        score=7.5,
        critique="Solid but risky.",
        dimensions={
            "feasibility": 8,
            "novelty": 6,
            "impact": 7,
            "effort": 5,
            "fit": 9,
        },
    )


@pytest.mark.parametrize("raw_score", [15.0, -3.0])
async def test_evaluate_clamps_out_of_range_score(raw_score: float) -> None:
    llm = FakeLLMClient.from_json(
        [{"score": raw_score, "critique": "x", "dimensions": {}}]
    )

    result = await evaluate(
        llm,
        goal="Ship the feature",
        candidate_title="A",
        candidate_content="Do A",
    )

    assert 0.0 <= result.score <= 10.0


async def test_parse_json_retries_and_succeeds_on_second_reply() -> None:
    llm = FakeLLMClient(completions=["not json", '{"candidates":[]}'])

    result = await parse_json(
        llm,
        system="sys",
        prompt="prompt",
        model_cls=ExpandResult,
    )

    assert result == ExpandResult(candidates=[])
    assert len(llm.calls) == 2


async def test_parse_json_raises_step_error_when_all_replies_bad() -> None:
    llm = FakeLLMClient(completions=["not json", "still not json", "nope"])

    with pytest.raises(StepError):
        await parse_json(
            llm,
            system="sys",
            prompt="prompt",
            model_cls=ExpandResult,
            retries=2,
        )

    assert len(llm.calls) == 3
