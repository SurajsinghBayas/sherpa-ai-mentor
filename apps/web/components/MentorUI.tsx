"use client";
import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Citation = { file: string; start_line: number; end_line: number; snippet: string };

export default function MentorUI() {
  const [repoId, setRepoId] = useState("");
  const [ingestInput, setIngestInput] = useState("https://github.com/gothinkster/realworld");
  const [question, setQuestion] = useState("How does user signup work?");
  const [answer, setAnswer] = useState("");
  const [cites, setCites] = useState<Citation[]>([]);
  const [overview, setOverview] = useState<any>(null);
  const [tour, setTour] = useState<any>(null);
  const [tasks, setTasks] = useState<any>(null);
  const [busy, setBusy] = useState("");

  async function post(path: string, body: any) {
    const r = await fetch(`${API}${path}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${path} → ${r.status}: ${await r.text()}`);
    return r.json();
  }

  async function doIngest() {
    setBusy("Indexing repo…");
    try {
      const j = await post("/api/ingest", { repo_url: ingestInput });
      setRepoId(j.repo_id);
    } catch (e: any) { alert(e.message); } finally { setBusy(""); }
  }

  async function doAsk() {
    if (!repoId) return alert("Ingest a repo first");
    setBusy("Sherpa is reading the code…");
    try {
      const j = await post("/api/ask", { repo_id: repoId, question });
      setAnswer(j.answer_markdown); setCites(j.citations || []);
    } catch (e: any) { alert(e.message); } finally { setBusy(""); }
  }

  async function doOverview() {
    setBusy("Mapping architecture…");
    try { setOverview(await post("/api/overview", { repo_id: repoId })); }
    catch (e: any) { alert(e.message); } finally { setBusy(""); }
  }

  async function doTour() {
    setBusy("Building guided tour…");
    try { setTour(await post("/api/tours", { repo_id: repoId, flow: question })); }
    catch (e: any) { alert(e.message); } finally { setBusy(""); }
  }

  async function doTasks() {
    setBusy("Scouting starter tasks…");
    try { setTasks(await post("/api/tasks", { repo_id: repoId, level: "beginner" })); }
    catch (e: any) { alert(e.message); } finally { setBusy(""); }
  }

  return (
    <main style={{ maxWidth: 980, margin: "0 auto", padding: 24 }}>
      <h1>🏔️ Sherpa — AI Codebase Mentor</h1>
      <p style={{ color: "#555" }}>Every answer cites the exact <code>file:line</code> it came from. No hallucinations.</p>

      <section style={card}>
        <h3>1 · Index a repo</h3>
        <div style={{ display: "flex", gap: 8 }}>
          <input value={ingestInput} onChange={(e) => setIngestInput(e.target.value)} style={input} />
          <button onClick={doIngest} style={btn}>Index</button>
        </div>
        {repoId && <p>✅ repo_id: <code>{repoId}</code></p>}
      </section>

      <section style={card}>
        <h3>2 · Ask anything</h3>
        <div style={{ display: "flex", gap: 8 }}>
          <input value={question} onChange={(e) => setQuestion(e.target.value)} style={input} />
          <button onClick={doAsk} style={btn}>Ask Sherpa</button>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button onClick={doOverview} style={btn2}>Architecture overview</button>
          <button onClick={doTour} style={btn2}>Guided tour</button>
          <button onClick={doTasks} style={btn2}>Starter tasks</button>
        </div>
        {busy && <p>⏳ {busy}</p>}
      </section>

      {answer && (
        <section style={card}>
          <h3>Sherpa says</h3>
          <pre style={{ whiteSpace: "pre-wrap" }}>{answer}</pre>
          <h4>Citations (click to verify in your checkout)</h4>
          {cites.map((c, i) => (
            <div key={i} style={cite}>
              <code>{c.file}:{c.start_line}-{c.end_line}</code>
              <pre style={{ whiteSpace: "pre-wrap", margin: "6px 0 0" }}>{c.snippet}</pre>
            </div>
          ))}
        </section>
      )}

      {overview && (
        <section style={card}>
          <h3>Architecture</h3>
          <p>{overview.summary}</p>
          <pre style={code}>{overview.mermaid}</pre>
          <ul>{overview.components?.map((c: any, i: number) => <li key={i}><b>{c.name}</b> — {c.path} ({c.role})</li>)}</ul>
        </section>
      )}

      {tour && (
        <section style={card}>
          <h3>{tour.title} (~{tour.estimated_minutes} min)</h3>
          {tour.steps?.map((s: any, i: number) => (
            <div key={i} style={cite}>
              <b>{s.caption}</b>
              <pre style={code}>{s.code}</pre>
            </div>
          ))}
        </section>
      )}

      {tasks && (
        <section style={card}>
          <h3>Starter tasks</h3>
          {tasks.tasks?.map((t: any, i: number) => (
            <div key={i} style={cite}>
              <b>{t.title}</b> <span style={{ color: "#666" }}>[{t.difficulty}]</span>
              <p>{t.why}</p>
              <p><code>{(t.files || []).join(", ")}</code></p>
              <ol>{(t.steps || []).map((s: string, j: number) => <li key={j}>{s}</li>)}</ol>
            </div>
          ))}
        </section>
      )}
    </main>
  );
}

const card: React.CSSProperties = { border: "1px solid #e5e5e5", borderRadius: 12, padding: 16, marginTop: 16 };
const input: React.CSSProperties = { flex: 1, padding: 10, borderRadius: 8, border: "1px solid #ccc" };
const btn: React.CSSProperties = { padding: "10px 16px", borderRadius: 8, background: "#111", color: "#fff", border: 0, cursor: "pointer" };
const btn2: React.CSSProperties = { padding: "8px 12px", borderRadius: 8, background: "#f0f0f0", border: "1px solid #ddd", cursor: "pointer" };
const cite: React.CSSProperties = { background: "#fafafa", border: "1px solid #eee", borderRadius: 8, padding: 10, marginTop: 8 };
const code: React.CSSProperties = { background: "#111", color: "#eee", padding: 12, borderRadius: 8, overflowX: "auto" };
