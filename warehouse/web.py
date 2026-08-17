from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from phonology import LANGUAGE_PHONOLOGY, phonology_dto
from schema import LANGUAGES, WORDNET_POS_TO_OURS
from warehouse.export_json import build_catalog, export_json
from warehouse.ingest.readings import ingest_readings
from warehouse.ingest.seed import seed_reference_data
from warehouse.ingest.wiktionary import ingest_wiktionary
from warehouse.ingest.wordfreq import ingest_wordfreq
from warehouse.ingest.wordnet_omw import ingest_omw, ingest_wordnet
from warehouse.jobs import snapshot, start
from warehouse.queries import get_concept, search_catalog, warehouse_stats
from warehouse.rank import compute_ranks

ROOT = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(ROOT / "web" / "templates"))
app = FastAPI(title="Lexicon Console", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(ROOT / "web" / "static")), name="static")

NAV = (
    ("/", "Coverage"),
    ("/catalog", "Catalog"),
    ("/export", "Export"),
    ("/ops", "Operations"),
)

OPS = (
    ("rank", "Rebuild ranks", "Safe. Seconds."),
    ("export-union", "Export union JSON", "Writes out/core_vocabulary.json"),
    ("export-zh-3000", "Export ZH 3000 pack", "Writes out/core_vocabulary.zh-3000.json"),
    ("wordfreq", "Ingest wordfreq", "Overwrites frequency ranks"),
    ("readings", "Ingest readings", "Fills declared phonology slots"),
    ("omw", "Ingest OMW", "Long. Gold alignments."),
    ("wiktionary", "Ingest Wiktionary", "Long. Gap fill."),
    ("wordnet", "Ingest WordNet", "Reload synsets"),
    ("seed", "Reseed languages", "Reference rows only"),
)


def _ctx(request: Request, **extra):
    return {"request": request, "nav": NAV, "languages": LANGUAGES, **extra}


@app.get("/", response_class=HTMLResponse)
def coverage(request: Request):
    stats = warehouse_stats()
    max_fill = max((row["filled"] for row in stats["coverage"]), default=1) or 1
    return templates.TemplateResponse(request, "coverage.html", _ctx(request, stats=stats, max_fill=max_fill, title="Coverage"))


@app.get("/catalog", response_class=HTMLResponse)
def catalog(
    request: Request,
    lang: str = Query("zh"),
    q: str = Query(""),
    max_rank: int = Query(3000),
    page: int = Query(1, ge=1),
):
    if lang not in LANGUAGES:
        lang = "zh"
    max_rank = min(max(max_rank, 1), 50000)
    limit = 40
    rows, total = search_catalog(lang, q, max_rank, limit=limit, offset=(page - 1) * limit)
    pages = max((total + limit - 1) // limit, 1)
    return templates.TemplateResponse(
        request,
        "catalog.html",
        _ctx(
            request,
            title="Catalog",
            lang=lang,
            q=q,
            max_rank=max_rank,
            rows=rows,
            total=total,
            page=page,
            pages=pages,
            pos_map=WORDNET_POS_TO_OURS,
        ),
    )


@app.get("/catalog/{synset_id}", response_class=HTMLResponse)
def concept(request: Request, synset_id: str):
    data = get_concept(synset_id)
    if data is None:
        raise HTTPException(404, "Concept not found")
    phonology = phonology_dto(LANGUAGES)
    return templates.TemplateResponse(
        request,
        "concept.html",
        _ctx(
            request,
            title=synset_id,
            synset=data["synset"],
            terms=data["terms"],
            phonology=phonology,
            systems=LANGUAGE_PHONOLOGY,
            pos_map=WORDNET_POS_TO_OURS,
        ),
    )


@app.get("/export", response_class=HTMLResponse)
def export_form(request: Request):
    return templates.TemplateResponse(request, "export.html", _ctx(request, title="Export", default_pivot="zh", default_n=3000))


@app.post("/export/preview")
def export_preview(
    pivot: str = Form(...),
    top_n: int = Form(...),
    target_langs: list[str] = Form(None),
):
    if pivot not in LANGUAGES:
        raise HTTPException(400, "Unknown pivot language")
    top_n = min(max(int(top_n), 1), 20000)
    catalog = build_catalog(top_n=top_n, pivot=pivot, target_langs=target_langs)
    
    # Return summary + sample 10 items
    sample = catalog["concepts"][:10]
    return {
        "pivot": catalog.get("pivot"),
        "topN": catalog.get("topN"),
        "count": catalog["count"],
        "languages": catalog["languages"],
        "sample_count": len(sample),
        "sample": sample,
    }


@app.post("/export")
def export_download(
    pivot: str = Form(...),
    top_n: int = Form(...),
    fmt: str = Form("json"),
    target_langs: list[str] = Form(None),
):
    if pivot not in LANGUAGES:
        raise HTTPException(400, "Unknown pivot language")
    top_n = min(max(int(top_n), 1), 20000)
    catalog = build_catalog(top_n=top_n, pivot=pivot, target_langs=target_langs)
    import gzip
    import json

    raw = json.dumps(catalog, ensure_ascii=False, indent=2).encode("utf-8")
    if fmt == "gz":
        payload = gzip.compress(raw)
        media = "application/gzip"
        name = f"core_vocabulary.{pivot}-{catalog['count']}.json.gz"
    else:
        payload = raw
        media = "application/json"
        name = f"core_vocabulary.{pivot}-{catalog['count']}.json"
    return Response(
        content=payload,
        media_type=media,
        headers={"Content-Disposition": f"attachment; filename={quote(name)}"},
    )


def _job(name: str) -> None:
    if name == "rank":
        compute_ranks(12000)
    elif name == "export-union":
        export_json(top_n=12000)
    elif name == "export-zh-3000":
        export_json(top_n=3000, pivot="zh")
    elif name == "wordfreq":
        ingest_wordfreq()
    elif name == "readings":
        ingest_readings()
    elif name == "omw":
        ingest_omw()
    elif name == "wiktionary":
        ingest_wiktionary()
    elif name == "wordnet":
        ingest_wordnet()
    elif name == "seed":
        seed_reference_data()
    else:
        raise ValueError(name)


@app.get("/ops", response_class=HTMLResponse)
def ops(request: Request):
    return templates.TemplateResponse(request, "ops.html", _ctx(request, title="Operations", ops=OPS, job=snapshot()))


@app.post("/ops/run")
def ops_run(name: str = Form(...)):
    allowed = {item[0] for item in OPS}
    if name not in allowed:
        raise HTTPException(400, "Unknown job")
    error = start(name, lambda: _job(name))
    if error:
        raise HTTPException(409, error)
    return RedirectResponse("/ops", status_code=303)


def run(host: str = "127.0.0.1", port: int = 8787) -> None:
    import uvicorn

    uvicorn.run("warehouse.web:app", host=host, port=port, reload=False)
