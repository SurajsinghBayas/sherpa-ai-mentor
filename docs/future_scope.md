# Future scope

What comes after the hackathon build, in the order we'd ship it. Each item says what it builds on that already exists, so the effort estimates are honest.

**Already shipped:** cited Q&A, architecture overview, guided tours, starter tasks, living docs, local uploads + CLI, macOS app, Amazon Polly voice (narrated tours, Listen, hands-free voice mode with talk-to-interrupt), chats saved on the device, syntax-highlighted code viewer.

## 1. Visualisation

The analysis step already computes a file-level import graph (with the line of every import), components, entry points and per-file symbols (`services/api/app/analysis.py`). Today only a static Mermaid diagram uses it, so most of this is frontend work.

| # | Feature | What it does | Builds on | Effort |
|---|---|---|---|---|
| 1 | **Interactive architecture map** | Components as nodes, imports as edges weighted by count. Click a component to expand into its files, click an edge to open the code viewer at the import line. Hover highlights neighbours; search flies to a file. React Flow (`@xyflow/react`, MIT) + `elkjs` auto-layout. | `Analysis.edges`, `components` | ~1 day |
| 2 | **Tour path on the map** | Building or narrating a tour lights up its route (UI → API → logic → data); a marker walks the edges in step with the voice. | #1, tours, narration | ~½ day |
| 3 | **Answer provenance map** | After each answer, a mini-map highlights the files it cited. Shows grounding visually. | #1, citations | ~½ day |
| 4 | **Codebase treemap** | Folders as nested rectangles sized by lines of code, coloured by layer; drill down, open files. `d3-hierarchy` (ISC). | file list, layers | ~½ day |
| 5 | **Change impact ("blast radius")** | Pick a file → everything that depends on it within 1–2 hops. Starter tasks show "touches 3 files, 7 depend on them". | `Analysis.edges` | ~½ day |
| 6 | **Learning progress map** | Shades the files and components a user has read (tours, citations, code viewer) and shows "42% of the core explored". Stored with chats on the device. | chat history store | ~½ day |

Later, not now: git hotspots (churn × complexity) need the `.git` folder, which ZIP uploads usually lack; 3D graphs look good once and read badly.

## 2. Voice

| Feature | Why | Notes |
|---|---|---|
| **Streaming answers** | The remaining voice delay is the LLM writing the whole answer (~6s). Stream tokens and speak each sentence as it completes. | Grounding check runs on the full answer; mark sentences as verified after. |
| **True barge-in with echo cancellation** | Talk-to-interrupt works by telling Sherpa's own voice apart from the user's words; on loud speakers it can misfire. | `getUserMedia` with echo cancellation + Silero VAD (`@ricky0123/vad-web`, MIT). |
| **Amazon Transcribe streaming** | Browser speech recognition is missing in Firefox and unreliable in some desktop webviews. | Same AWS account as Polly. |
| **Indian languages** | Explanations in Hindi and other languages for new joiners who prefer them. | Polly has Hindi neural voices (e.g. Kajal); answers already come from an LLM that can write in Hindi. |
| **Speech marks** | Highlight each line in the code viewer at the moment it's mentioned. | Polly speech marks (word/sentence timings). |

## 3. Chats and memory

- **Sync to the account**: chats are on the device today (10-year retention, IndexedDB). Add server storage so they follow the user between the web and desktop apps, with export and delete.
- **Team knowledge**: pin good answers so the next joiner sees them first ("asked 12 times this month").

## 4. Product

- **Pull-request explainer**: summarise a PR against the architecture map, list affected components, link every claim to lines.
- **IDE extension (VS Code)**: ask Sherpa from the editor; citations open in the editor instead of the drawer.
- **Slack / Teams bot**: the same cited answers where teams already ask questions.
- **Manager view**: onboarding progress across a team, common questions, docs that keep going stale.
- **Self-hosted / on-prem**: the API already runs on any OpenAI-compatible endpoint or Ollama; package it as one Docker image with Postgres + pgvector.

## 5. Desktop and production

- **Windows build**: same code; switch `build:desktop` env handling to `cross-env`, add Windows code signing.
- **Signing, notarisation and auto-update** for macOS (`apps/desktop/README.md` has the checklist).
- **Content Security Policy** for the desktop app once the API is deployed.
- **Point the app at the deployed API** (`SHERPA_API_URL=… make desktop-build`).
