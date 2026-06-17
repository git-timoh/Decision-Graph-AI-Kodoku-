"""Pure step functions: take an `LLMClient` plus plain inputs, return structured data.

Steps never touch the DB and never emit events — that is the `DecisionEngine`'s job.
"""
from __future__ import annotations
