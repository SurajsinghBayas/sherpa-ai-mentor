# Demo script (5 min, judge-friendly)

1. **Hook (30s):** "New hires take weeks to onboard. Docs are stale, seniors are busy. Sherpa reads the repo and mentors with citations you can click."
2. **Index (45s):** `POST /api/ingest` RealWorld. Show files/chunks count.
3. **Ask (60s):** "How does user signup work?" → answer with 3-5 `[file:line]` chips. Click one, show the code.
4. **Overview (45s):** `POST /api/overview` → mermaid graph + components. "This is the map."
5. **Tour (60s):** `POST /api/tours {flow: user signup}` → step through route → service → model.
6. **Tasks (30s):** `POST /api/tasks` → 3 starter tasks with files + steps. "First PR in day one."
7. **Grounding flex (30s):** show a dropped ghost citation note + `make test` passing. "It refuses to hallucinate."

Backup if offline: `POST /api/ingest-self` indexes Sherpa itself; ask "How are citations verified?"
