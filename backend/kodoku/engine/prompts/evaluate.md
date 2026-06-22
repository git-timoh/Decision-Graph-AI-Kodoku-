You are critically evaluating one candidate idea toward a goal.

Goal: $goal

Candidate:
Title: $candidate_title
Content: $candidate_content

Score the candidate from 0 (worthless) to 10 (excellent) on its overall merit
toward the goal, write a brief critique, and rate it on each of these
dimensions from 0 to 10: feasibility, novelty, impact, effort, fit.

Return ONLY valid JSON matching this schema, with no other text:

{"score": 0-10, "critique": "...", "dimensions": {"feasibility": 0-10, "novelty": 0-10, "impact": 0-10, "effort": 0-10, "fit": 0-10}}
