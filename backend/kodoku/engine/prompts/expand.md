You are exploring possible next steps toward a goal using Tree-of-Thoughts reasoning.

Goal: $goal

Current idea (parent node):
Title: $parent_title
Content: $parent_content

Propose exactly $branching_factor distinct, concrete candidate next steps that
build on the current idea and move toward the goal. Each candidate must be
meaningfully different from the others.

Return ONLY valid JSON matching this schema, with no other text:

{"candidates": [{"title": "...", "content": "..."}]}
