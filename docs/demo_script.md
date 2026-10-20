# Demo script (5 min)

Pre-index `https://github.com/fastapi/full-stack-fastapi-template` before going on stage. Indexing takes about 10 s, and the first overview takes about 30 s.

1. **Hook (30s):** "New hires take weeks to onboard. Docs go stale and seniors are busy. Sherpa reads the repo and teaches it, and every claim links to the exact lines."
2. **Architecture (60s):** open **Architecture**. Show the Mermaid map built from the real import graph (edge labels are import counts), then the component cards. Click a citation chip to open the code drawer at those lines.
3. **Tour (60s):** **Code Tours** → "What happens when a user signs up?" Step through the frontend form → `useAuth` → API route → `crud.create_user` → model.
4. **Ask (60s):** "Where are passwords hashed and how is login verified?" Point at the **verified sources** badge and the model badge. Ask a follow-up ("and where is the token checked?") to show conversation context.
5. **Starter tasks (30s):** show five first-PR tasks, each with files, steps and effort.
6. **Living docs (45s):** generate the guide. Index a local copy instead (`make api` allows local paths), edit one cited file, then click **Sync with code**. Only the affected section is flagged and rewritten, and the changelog records it.
7. **Proof (15s):** `make eval` results (98% citation validity, 10/10 grounded) and the **User study** page with the recorded sessions.

Backup if the LLM is unreachable: everything still works in offline mode (badge shows "offline fallback"). `POST /api/ingest-self` indexes Sherpa itself; then ask "How are citations verified?"
