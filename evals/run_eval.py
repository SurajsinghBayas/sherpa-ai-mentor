"""Grounding eval — runs the golden questions through the real pipeline and reports:

- citation validity: share of model citations that exist in the snapshot (verifier keeps/drops)
- grounded answers: answers with >= 1 verified citation
- expected-file hit rate: answer cites a file a maintainer would point to
- latency and how often the offline fallback answered

Usage (from services/api):  python ../../evals/run_eval.py [--repo-id ID] [--out FILE]
--repo-id evaluates a snapshot already indexed in the database (pgvector embeddings when
on Postgres); without it the repo is cloned into memory and searched with TF-IDF.
Writes evals/results.md. Uses the server's configured LLM (see .env).
"""
import argparse
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "services", "api"))

from app.agents.mentor import answer_question  # noqa: E402
from app.ingest import ingest_source  # noqa: E402
from app.llm import llm  # noqa: E402
from app.persist import SqlBackend, vectors_supported  # noqa: E402
from app.embeddings import embedder  # noqa: E402
from app.store import RepoStore  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-id", help="use a snapshot already indexed in the database")
    ap.add_argument("--out", default="results.md", help="output file under evals/")
    args = ap.parse_args()
    golden = json.load(open(os.path.join(HERE, "golden_qa.json")))

    if args.repo_id:
        store = RepoStore(args.repo_id, SqlBackend(args.repo_id))
        if not store.chunks:
            sys.exit(f"repo {args.repo_id} is not in the database")
        retrieval = (f"keyword + pgvector (`{embedder.model}`)"
                     if vectors_supported() and embedder.available else "keyword + TF-IDF")
    else:
        print(f"cloning {golden['repo_url']} …")
        rid, chunks, meta, sources = ingest_source(golden["repo_url"], None, "")
        store = RepoStore(rid)
        store.save(chunks, meta, sources)
        retrieval = "keyword + TF-IDF (in memory)"
    files = set(store.files())

    rows = []
    for item in golden["questions"]:
        t = time.time()
        r = answer_question(store, item["q"])
        dt = time.time() - t
        cited = {c["file"] for c in r["citations"]} if r["verify"]["verified"] else set()
        expected = [f for f in item["expect_files"] if f in files]
        rows.append({
            "q": item["q"], "mode": r["mode"], "seconds": round(dt, 1),
            "verified": r["verify"]["verified"], "dropped": len(r["verify"]["unchecked_claims"]),
            "hit": bool(cited & set(expected)), "expected_present": bool(expected),
            "cited": sorted(cited),
        })
        print(f"{'HIT ' if rows[-1]['hit'] else 'MISS'} {dt:5.1f}s v={rows[-1]['verified']} d={rows[-1]['dropped']} {item['q']}")

    v = sum(r["verified"] for r in rows)
    d = sum(r["dropped"] for r in rows)
    scored = [r for r in rows if r["expected_present"]]
    summary = {
        "questions": len(rows),
        "citation_validity": round(v / (v + d), 3) if v + d else None,
        "grounded_answers": sum(r["verified"] > 0 for r in rows),
        "expected_file_hit_rate": round(sum(r["hit"] for r in scored) / len(scored), 3) if scored else None,
        "median_seconds": statistics.median(r["seconds"] for r in rows),
        "offline_fallbacks": sum(r["mode"] == "offline" for r in rows),
        "model": llm.model if llm.available else "offline",
        "retrieval": retrieval,
    }
    print(json.dumps(summary, indent=2))

    out = [f"# Grounding eval — {store.meta.get('name', store.repo_id)}", "",
           f"_Run {time.strftime('%Y-%m-%d %H:%M')} · model `{summary['model']}` · retrieval {retrieval} · "
           f"commit `{store.meta.get('commit', '')}`. Regenerate with `make eval`._", "",
           "| Metric | Value |", "|---|---|",
           f"| Questions | {summary['questions']} |",
           f"| Citation validity (verified / all cited) | {summary['citation_validity']:.0%} ({v} kept, {d} removed) |"
           if summary["citation_validity"] is not None else "| Citation validity | n/a |",
           f"| Answers with ≥1 verified citation | {summary['grounded_answers']}/{len(rows)} |",
           f"| Cites the file a maintainer would point to | {summary['expected_file_hit_rate']:.0%} |"
           if summary["expected_file_hit_rate"] is not None else "| Expected-file hit rate | n/a |",
           f"| Median latency | {summary['median_seconds']} s |",
           f"| Offline fallbacks | {summary['offline_fallbacks']} |", "",
           "| Question | Hit | Verified | Removed | Seconds | Cited files |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['q']} | {'✅' if r['hit'] else '❌'} | {r['verified']} | {r['dropped']} | "
                   f"{r['seconds']} | {', '.join('`' + f + '`' for f in r['cited'][:4])} |")
    with open(os.path.join(HERE, args.out), "w") as f:
        f.write("\n".join(out) + "\n")
    print(f"wrote evals/{args.out}")


if __name__ == "__main__":
    main()
