STAGE: EVAL

Score the idea in idea.md. Be honest and terse. Ask {NAME} at most three
clarifying questions if the idea is too thin to score; otherwise score now.

Scores 0-5:
- complexity   (5 = huge)
- value
- niche        (5 = defensible, {NAME} has unfair knowledge; 0 = crowded, no edge)
- reuse        (what {NAME}'s existing projects already cover; guess if unknown)
- distribution (does {NAME} already know who it is for and where they are)
- track        knowledge ({NAME} must learn it, serial) or product (LLMs churn it, parallel)

Personal tools (audience = {NAME}): distribution is 5 (known audience, known place). Niche then carries the weight: how specifically it fits {NAME}'s situation / unfair knowledge.
Pass rule: value + niche + distribution >= 10 AND complexity <= 4 -> go.
7-9 -> park. Below -> kill.

Write eval.md in exactly this shape:

---
complexity: N
value: N
niche: N
reuse: N
distribution: N
track: knowledge|product
decision: go|park|kill
---
## Rationale
(two lines max)
## Risks
(bullets, max 3)
## Questions for {NAME}
(bullets, or "none")

Then show {NAME} the scores as a single compact table and the decision, and ask
"agree / disagree?". If {NAME} disagrees, adjust and rewrite eval.md.
