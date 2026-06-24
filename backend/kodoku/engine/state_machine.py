"""The DecisionEngine: the stateful Tree-of-Thoughts loop.

This wires the pure steps (expand/evaluate/decide/synthesize) into a frontier
BFS over candidate nodes, persisting `Node`/`Evaluation` rows and emitting an
event for every observable transition. It never commits — the single commit
happens at the run boundary (Task 5). Each ORM write is `flush()`ed so it is
visible within the session (and to the recording emitter in tests).
"""
from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kodoku.api.dtos import SessionConfig
from kodoku.db.models import Checkpoint, Evaluation, Node
from kodoku.db.models import Session as SessionModel
from kodoku.domain.enums import CheckpointKind, NodeKind, NodeStatus, SessionStatus
from kodoku.engine.events import (
    BUDGET_EXCEEDED,
    CHECKPOINT_REACHED,
    COST_UPDATED,
    DECIDE_COMPLETED,
    ENGINE_STATE_CHANGED,
    EVALUATION_COMPLETED,
    NODE_CREATED,
    NODE_UPDATED,
    SESSION_DONE,
    SESSION_ERROR,
    SESSION_STARTED,
    SYNTHESIS_COMPLETED,
    SYNTHESIS_STREAMING,
    Emitter,
)
from kodoku.engine.frontier import rebuild_frontier
from kodoku.engine.steps.decide import Decision, decide
from kodoku.engine.steps.evaluate import EvaluationResult, evaluate
from kodoku.engine.steps.expand import expand
from kodoku.engine.steps.judge import JudgeCandidate, decide_with_judge
from kodoku.engine.steps.synthesize import synthesize
from kodoku.llm.factory import RoleClients

#: Max concurrent `evaluate` LLM calls per parent.
# ponytail: hardcoded module constant — make configurable later.
EVAL_CONCURRENCY = 4


class DecisionEngine:
    def __init__(
        self,
        db: AsyncSession,
        session: SessionModel,
        clients: RoleClients,
        emit: Emitter,
        *,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> None:
        self.db = db
        self.session = session
        self.clients = clients
        self.emit = emit
        self.should_stop = should_stop
        self.config = SessionConfig(**session.config)
        self._frontier: deque[UUID] = deque()
        self._paused = False
        self._budget_exceeded = False
        self._cost_base = float(session.cost_usd or 0)

    async def run(self) -> None:
        try:
            await self._run()
        except Exception as exc:  # noqa: BLE001 — persist failure, then re-raise
            try:
                self.session.status = SessionStatus.ERROR.value
                self.session.current_step = None
                await self.db.flush()
                await self.emit(SESSION_ERROR, {"message": str(exc)})
                await self.db.flush()
            except Exception:  # noqa: BLE001 — don't mask the original error
                pass
            raise

    async def _run(self) -> None:
        # 1. Seed.
        self.session.status = SessionStatus.RUNNING.value
        self.session.current_step = "expanding"
        await self.db.flush()
        await self.emit(SESSION_STARTED, {})
        await self._state_changed("root", "expanding")

        self._frontier = await rebuild_frontier(self.db, self.session)
        await self.db.flush()

        # 2. Frontier BFS.
        while (
            self._frontier
            and not self.should_stop()
            and not self._paused
            and not self._budget_exceeded
        ):
            await self._expand_one(self._frontier.popleft())
            await self._update_cost_and_check_budget()

        # 2b. Paused for human review at a checkpoint — stop before synthesis.
        # Status/current_step were already set to AWAITING_HUMAN by the pause.
        if self._paused:
            return

        # Budget hit — stop before synthesis, mirroring the _paused path.
        if self._budget_exceeded:
            self.session.status = SessionStatus.PAUSED.value
            self.session.current_step = None
            await self.db.flush()
            return

        # 3. Cooperative stop.
        if self.should_stop():
            self.session.status = SessionStatus.PAUSED.value
            self.session.current_step = None
            await self.db.flush()
            return

        # 4 + 5. Synthesis and done.
        await self._synthesize()
        self.session.status = SessionStatus.DONE.value
        self.session.current_step = None
        await self.db.flush()
        await self.emit(SESSION_DONE, {})

    async def _expand_one(self, parent_id: UUID) -> None:
        parent = await self._node(parent_id)
        cands = await expand(
            self.clients.expand,
            goal=self.session.goal,
            parent_title=parent.title,
            parent_content=parent.content,
            branching_factor=self.config.branching_factor,
        )

        if not cands:
            # Empty-candidates guard: never call evaluate/decide on nothing.
            await self._mark(parent, NodeStatus.EXPANDED)
            await self.db.flush()
            return

        children: list[Node] = []
        for cand in cands:
            child = Node(
                session_id=self.session.id,
                parent_id=parent.id,
                depth=parent.depth + 1,
                kind=NodeKind.CANDIDATE.value,
                title=cand.title,
                content=cand.content,
                status=NodeStatus.ACTIVE.value,
            )
            self.db.add(child)
            children.append(child)
        await self.db.flush()

        for child in children:
            await self.emit(
                NODE_CREATED,
                {
                    "id": str(child.id),
                    "session_id": str(child.session_id),
                    "parent_id": str(child.parent_id),
                    "depth": child.depth,
                    "kind": child.kind,
                    "title": child.title,
                    "content": child.content,
                    "status": child.status,
                },
            )

        # Evaluate children concurrently (bounded), but persist the rows and
        # emit events sequentially in child order below.
        sem = asyncio.Semaphore(EVAL_CONCURRENCY)

        async def _eval_child(child: Node) -> EvaluationResult:
            async with sem:
                return await evaluate(
                    self.clients.evaluate,
                    goal=self.session.goal,
                    candidate_title=child.title,
                    candidate_content=child.content,
                )

        results = await asyncio.gather(*(_eval_child(child) for child in children))

        scored: list[tuple[UUID, float]] = []
        for child, ev in zip(children, results, strict=True):
            evaluation = Evaluation(
                node_id=child.id,
                score=Decimal(str(ev.score)),
                critique=ev.critique,
                dimensions=ev.dimensions,
                model=self.clients.evaluate.model,
            )
            self.db.add(evaluation)
            await self.db.flush()
            await self.emit(
                EVALUATION_COMPLETED,
                {
                    "node_id": str(child.id),
                    "score": ev.score,
                    "critique": ev.critique,
                    "dimensions": ev.dimensions,
                },
            )
            scored.append((child.id, ev.score))

        if self.config.decide_mode == "judge":
            judge_cands = [
                JudgeCandidate(
                    id=child.id, title=child.title, content=child.content,
                    score=ev.score, critique=ev.critique, dimensions=ev.dimensions,
                )
                for child, ev in zip(children, results, strict=True)
            ]
            outcome = await decide_with_judge(
                self.clients.evaluate, goal=self.session.goal,
                candidates=judge_cands, depth=parent.depth + 1,
                max_depth=self.config.max_depth,
            )
            decision, rationale, source = outcome.decision, outcome.rationale, outcome.source
        else:
            decision = decide(scored, depth=parent.depth + 1, max_depth=self.config.max_depth)
            rationale, source = "", "threshold"

        await self.emit(
            DECIDE_COMPLETED,
            {
                "parent_id": str(parent.id),
                "keep": [str(cid) for cid in decision.keep],
                "prune": [str(cid) for cid in decision.prune],
                "rationale": rationale,
                "source": source,
            },
        )

        if self.config.hitl_mode == "every_branch":
            await self._pause_for_checkpoint(parent, children, results, decision)
            return

        kept = set(decision.keep)
        for child in children:
            status = NodeStatus.KEPT if child.id in kept else NodeStatus.PRUNED
            await self._mark(child, status)
        await self._mark(parent, NodeStatus.EXPANDED)
        await self.db.flush()

        self._frontier.extend(decision.expand)

    async def _update_cost_and_check_budget(self) -> None:
        """Sum per-role client cost onto the session and stop if over budget.

        ponytail: synthesis runs after the BFS loop, so its streaming cost is
        added to the total afterward but is not budget-gated. Acceptable: one
        cheap call, and the human is already reviewing a stopped run.
        """
        total = (
            self.clients.expand.cost_usd
            + self.clients.evaluate.cost_usd
            + self.clients.synthesize.cost_usd
        )
        self.session.cost_usd = Decimal(str(self._cost_base + total))
        await self.db.flush()
        budget = self.config.budget_usd
        await self.emit(
            COST_UPDATED,
            {"cost_usd": float(self.session.cost_usd), "budget_usd": budget},
        )
        if budget is not None and float(self.session.cost_usd) >= budget:
            self._budget_exceeded = True
            await self.emit(
                BUDGET_EXCEEDED,
                {"cost_usd": float(self.session.cost_usd), "budget_usd": budget},
            )

    async def _pause_for_checkpoint(
        self,
        parent: Node,
        children: list[Node],
        results: list[EvaluationResult],
        decision: Decision,
    ) -> None:
        """Persist a POST_EVALUATE checkpoint and stop the run for human review.

        Mirrors the kept/pruned classification `decide()` computed, but does not
        apply it: the parent is marked EXPANDED (so a future frontier rebuild
        won't re-expand it), while the candidate children stay ACTIVE pending
        resolution. The frontier is not extended and synthesis does not run.
        """
        keep_set = set(decision.keep)
        candidates = [
            {
                "id": str(child.id),
                "title": child.title,
                "content": child.content,
                "score": ev.score,
                "critique": ev.critique,
                "dimensions": ev.dimensions,
            }
            for child, ev in zip(children, results, strict=True)
        ]
        payload = {
            "proposed_keep": [str(cid) for cid in decision.keep],
            "proposed_prune": [str(child.id) for child in children if child.id not in keep_set],
            "candidates": candidates,
        }

        checkpoint = Checkpoint(
            session_id=self.session.id,
            kind=CheckpointKind.POST_EVALUATE.value,
            payload=payload,
            decision=None,
            resolved_at=None,
        )
        self.db.add(checkpoint)
        await self.db.flush()

        await self.emit(
            CHECKPOINT_REACHED,
            {
                "checkpoint_id": str(checkpoint.id),
                "kind": checkpoint.kind,
                "payload": payload,
            },
        )

        await self._mark(parent, NodeStatus.EXPANDED)
        self.session.status = SessionStatus.AWAITING_HUMAN.value
        self.session.current_step = None
        await self.db.flush()
        self._paused = True

    async def _synthesize(self) -> None:
        self.session.current_step = "synthesizing"
        await self.db.flush()
        await self._state_changed("expanding", "synthesizing")

        kept_nodes = await self._kept_nodes()
        kept = [(n.title, n.content) for n in kept_nodes]

        text = ""
        async for delta in synthesize(self.clients.synthesize, goal=self.session.goal, kept=kept):
            text += delta
            await self.emit(SYNTHESIS_STREAMING, {"delta": delta})

        self.session.final_synthesis = text
        await self.db.flush()
        await self.emit(SYNTHESIS_COMPLETED, {"text": text})

    async def _mark(self, node: Node, status: NodeStatus) -> None:
        node.status = status.value
        await self.emit(NODE_UPDATED, {"id": str(node.id), "status": node.status})

    async def _state_changed(self, from_: str, to: str) -> None:
        await self.emit(ENGINE_STATE_CHANGED, {"from": from_, "to": to})

    async def _node(self, node_id: UUID) -> Node:
        stmt = select(Node).where(Node.id == node_id)
        return (await self.db.execute(stmt)).scalar_one()

    async def _kept_nodes(self) -> list[Node]:
        stmt = (
            select(Node)
            .where(
                Node.session_id == self.session.id,
                Node.status == NodeStatus.KEPT.value,
            )
            .order_by(Node.depth.asc(), Node.created_at.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())
