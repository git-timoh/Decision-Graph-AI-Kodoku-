You are selecting which candidate ideas to keep versus prune toward a goal.

Goal: $goal

You are given sibling candidates that were each scored independently. Judge them
COMPARATIVELY: keep the ones most worth expanding toward the goal and prune the
rest. Keeping fewer, stronger candidates is better than keeping everything.

Candidates:
$candidates_block

Return ONLY valid JSON matching this schema, with no other text. Every candidate
id MUST appear in exactly one of "keep" or "prune". Keep at least one.

{"keep": ["<uuid>", ...], "prune": ["<uuid>", ...], "rationale": "one short paragraph comparing them"}
