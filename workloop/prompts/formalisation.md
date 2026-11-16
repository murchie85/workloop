STAGE: FORMALISATION

Read idea.md and eval.md. Map the idea into a crawlable template that agents
can traverse fast. {NAME} gives light-touch approval only, so produce it in one
pass and keep every section short.

Write formalisation.md:

---
track: knowledge|product
audience: "named community or person"
---
## Features
(numbered, one line each)
## Increments
(numbered; each one independently shippable and phrased as a prompt an agent could act on)
## Feature-complete checklist
- [ ] fully working end to end in a real environment
- [ ] write-up
- [ ] repo
- [ ] demo link
- [ ] audience named: ...
- [ ] anticipated "can you add X" requests: built or roadmapped with config
## Rollout config
(stages of release, what flag/config gates each)
## Reuse
(existing projects or code to pull from, if any)

ALSO write plan.html — the VISUAL version {NAME} approves from. Self-contained HTML, inline CSS only,
no external scripts/fonts/CDNs, dark theme (bg #0b0d12, text #f4f6fb, accent #ffcc00, green #22c55e,
red #ff5e5b). Poster, not document: title + one-line summary + eval scores as bars (from eval.md) +
a FLOW DIAGRAM of the solution (divs/CSS or inline SVG: components, data flow, new vs reused) +
a sketch of the end result + the increments as a numbered strip + rollout stages + risks (max 3) +
audience. Labels, not sentences. The CLI opens it in the browser when you finish.

Then show {NAME} a five-line summary and ask "approve / change?".
