from __future__ import annotations

import json
from warehouse.gloss_generator import load_gloss_cache
from warehouse.queries import get_concept, search_catalog


def test_search_catalog_includes_native_gloss():
    # Searching for catalog items in a language should include native_gloss if available in gloss_cache
    rows, total = search_catalog("vi", "", max_rank=50, limit=10, offset=0)
    assert len(rows) > 0
    # Every row should have 'native_gloss' field (either string or None)
    for r in rows:
        assert "native_gloss" in r


def test_search_catalog_distinct_headwords_toggle():
    # When distinct=True, every returned row must have a distinct 'text'
    rows, total = search_catalog("en", "", max_rank=500, limit=20, offset=0, distinct=True)
    assert len(rows) == 20
    texts = [r["text"] for r in rows]
    assert len(set(texts)) == len(texts)


from fastapi.testclient import TestClient
from warehouse.web import app


def test_export_endpoint_supports_sqlite():
    client = TestClient(app)
    res = client.post(
        "/export",
        data={
            "pivot": "vi",
            "top_n": "10",
            "fmt": "sqlite",
            "target_langs": ["vi", "en"],
        },
    )
    assert res.status_code == 200
    assert res.headers["content-type"] in ("application/gzip", "application/x-gzip", "application/octet-stream")
    assert "core_vocabulary.vi-10.db.gz" in res.headers["content-disposition"]
    assert len(res.content) > 100

