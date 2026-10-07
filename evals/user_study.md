# Stage-3 user study protocol (n=5 newcomers)

Goal: show newcomers understand the codebase faster **with** Sherpa.

## Setup
- Repo: RealWorld conduit API (or FastAPI official repo). Pre-indexed, same commit for all.
- Group A (control, n=2-3): repo + README only.
- Group B (sherpa, n=2-3): repo + Sherpa web UI.

## Tasks (30 min cap each)
1. Draw the architecture (3 boxes + arrows). Score 0-3 vs maintainer reference.
2. Explain signup flow in own words. Score: files named correctly (0-2) + order correct (0-2).
3. Pick a starter task and open a draft PR / detailed plan. Score: valid scope (0-2).

## Metrics
- Time-to-first-correct-architecture, time-to-explain-signup, task completion.
- Citation check: every Sherpa answer the user relied on must have ≥1 valid file:line.
- SUS-lite: 3 questions (useful / trustworthy / would use again), 1-5.

## Reporting
Record raw table in `docs/user_study_results.md` + one chart (bar: control vs sherpa minutes).
Honest reporting: include failures and quotes.
