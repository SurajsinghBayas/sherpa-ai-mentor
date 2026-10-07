"""Web enrichment tests — Firecrawl is mocked, no network, no key needed."""
from app import enrich


def test_candidate_urls_prefers_repo_page():
    urls = enrich.candidate_urls("https://github.com/org/repo.git",
                                 ["https://docs.example.com/guide", "not-a-url"])
    assert urls[0] == "https://github.com/org/repo"
    assert "https://docs.example.com/guide" in urls
    assert "not-a-url" not in urls


def test_web_path_is_stable_and_citable():
    p = enrich.web_path("https://github.com/org/repo")
    assert p.startswith("web/") and p.endswith(".md") and " " not in p


def test_enrich_skipped_without_key():
    chunks, sources = enrich.enrich_repo("https://github.com/org/repo", [],
                                         api_key="")
    assert chunks == [] and sources[0]["status"] == "skipped"


def test_enrich_chunks_scraped_markdown(monkeypatch):
    monkeypatch.setattr(enrich.settings, "firecrawl_api_key", "fc-test")
    monkeypatch.setattr(
        enrich, "firecrawl_scrape",
        lambda url, key, base_url=None: (
            f"# {url}\n\nSignup hits POST /signup which calls create_user."
            if "github" in url else None))
    chunks, sources = enrich.enrich_repo("https://github.com/org/repo",
                                         ["https://docs.example.com/dead"])
    assert sources[0]["status"] == "ok" and sources[1]["status"] == "failed"
    assert chunks and all(c.file.startswith("web/") for c in chunks)
    # enriched chunks are retrievable + citable like code
    from app.store import RepoStore
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        s = RepoStore(d, "web1")
        s.save(chunks, {"source": "test"})
        hits = s.search("how does signup work?", k=2)
        assert hits and hits[0][0].file.startswith("web/")
        from app.agents.mentor import verify_citations
        c = chunks[0]
        _, cites, dropped = verify_citations(
            s, f"See [{c.file}:{c.start_line}-{c.end_line}].")
        assert len(cites) == 1 and not dropped


def test_ingest_reports_web_sources_keyless(client):
    """End-to-end: no FIRECRAWL_API_KEY → ingest succeeds, code-only."""
    r = client.post("/api/ingest-self")
    assert r.status_code == 200
    body = r.json()
    assert body.get("web_sources", []) == []  # ingest-self is code-only by design
