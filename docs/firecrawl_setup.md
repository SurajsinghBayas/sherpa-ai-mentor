# Firecrawl web enrichment

Sherpa answers from **code first**. With Firecrawl configured, ingest also
pulls **web context** — the rendered GitHub repo page (description, topics,
README) plus any docs URLs you supply — chunked with `web/…` provenance so
claims cite exactly like code (`web/github.com/org/repo.md:12-20`).

## 1. Get a key

Sign up at [firecrawl.dev](https://www.firecrawl.dev) → API keys → copy `fc-…`.

## 2. Configure

```bash
export FIRECRAWL_API_KEY="fc-..."
# optional: self-hosted / proxy
# export FIRECRAWL_BASE_URL="https://your-firecrawl-proxy/v1"
```

Restart the API. The dashboard ingest card then shows
`+ N web source(s) via Firecrawl`; without a key it says
`code-only` and everything still works.

## 3. How it works

- `POST /api/ingest {repo_url, docs_urls[], enrich_web}` →
  `app/enrich.py::enrich_repo` scrapes up to 6 sources
  (`/v1/scrape`, markdown-only, main content, 15k chars cap each).
- Web markdown is chunked with the same splitter as docs, tagged role
  `web docs`, and merged into the repo snapshot before saving.
- Retrieval, tours, and the CitationVerifier treat `web/…` paths like any
  file — ghost web citations are rejected the same way.
- Enrichment runs **at ingest time only** (never on the Q&A hot path),
  and any scrape failure degrades to code-only per source.

## 4. Cost control

- One scrape per source per ingest (repo page + your docs URLs).
- Re-ingesting the same repo re-scrapes — index once, ask many times.
- For large doc sites, pass the 2–3 pages that matter instead of homepages.
