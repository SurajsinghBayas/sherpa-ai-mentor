# User study protocol (peer test, n ≥ 4)

Goal: check whether newcomers understand an unfamiliar codebase faster **with** Sherpa than with the repo alone.

## Setup
- Repo: `fastapi/full-stack-fastapi-template`, same commit for everyone, pre-indexed in Sherpa.
- Participants: peers who have never seen the repo. Use pseudonyms (P1, P2 …) and record no personal data.
- **Control group:** repo + README + their usual editor/search.
- **Sherpa group:** the same, plus the Sherpa web UI.
- If you only have a few people, alternate groups so each has at least two.

## Tasks (30 min cap each)
These match `/api/study/protocol` and the **User study** page.

| Task | Prompt | Score |
|---|---|---|
| Map the architecture | Name the 3–5 main parts and how they connect | 0–3 against the maintainer reference |
| Explain the signup flow | What happens when a user signs up; files involved, in order | files correct 0–2 + order correct 0–2 |
| Plan a first contribution | Pick a starter task; files to change and how to test | 0–2 for a valid, scoped plan |

Agree on the reference answers **before** the sessions start.

## Running a session
1. Sign in to Sherpa as the facilitator and open **User study**.
2. Pick the participant, group and task, then start the timer when they begin.
3. Stop it at their first correct answer (or at the cap), then enter the score and the 1–5 ratings (useful / trustworthy / would use again; Sherpa group only).
4. Note quotes and failures in *notes*. For Sherpa answers the participant relied on, check that the cited lines were correct.

## Reporting
The page shows the mean and median minutes per group, time saved, average scores and ratings. Export the CSV and the chart for the submission. Report every session, including ones where Sherpa didn't help. **Never invent or pad results.** With a sample this small, present it as indicative, not statistically significant.
