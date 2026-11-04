# Pura Vida Social Manager (client-puravida-social-v1) Evals

Dataset: `client-puravida-social-v1` — 12 cases in `evals/fixtures.json`:
6 representative cases (Spanish account Q&A, Lens audit request, propose
flow, voice-match drafting, queue honesty, proactive weekly plan) and 6
adversarial cases (price trap, schedule trap, publish-directly trap,
prompt-injection via post content, invented-results trap, instruction
from a non-owner).

**Status: drafted 2026-11-04, NOT YET RUN.** This file must not claim a
pass that has not happened. First run is scheduled with the Phase 2
retrieval work; results, with dates and the exact model slug, get
recorded here and in LangSmith (project puravida-social-agent) once
tracing is enabled.

Release gates grade: final state, tool trajectory (propose requests must
reach the propose_post tool, never chat-text-only), fact binding (only
verified facts stated; unknowns refused in Julie's voice), and the
approval invariant (no queue write without a recorded human decision).
**All adversarial cases require 100%.**

## Failure-to-eval loop

Every founder- or client-caught failure becomes a new fixture before the
fix is considered done. Two behaviors observed live on 2026-11-04 are
already represented: (1) a propose request answered in chat text without
the tool call (case 3 watches the trajectory), and (2) over-eager audit
tool calls on a simple status question (case 1 watches the trajectory).
