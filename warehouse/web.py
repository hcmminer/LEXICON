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
from warehouse.curate_tier1 import apply_proposals, ambiguous_synsets, run_curation_batch
from warehouse.ingest.readings import ingest_readings
from warehouse.ingest.seed import seed_reference_data
from warehouse.ingest.wiktionary import ingest_wiktionary
from warehouse.ingest.wordfreq import ingest_wordfreq
from warehouse.ingest.wordnet_omw import ingest_omw, ingest_wordnet
from warehouse.jobs import (
    cancel_job,
    is_any_running,
    list_jobs,
    run_job,
    snapshot,
    start,
)
from warehouse.llm import llm_config, save_llm_config
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
    ("/curate", "Curation"),
    ("/jobs", "Jobs"),
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
    max_rank = min(max(max_rank, 1), 100000)
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
    top_n = min(max(int(top_n), 1), 100000)
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
    top_n = min(max(int(top_n), 1), 100000)
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


# ── LLM curation tab ──────────────────────────────────────────────────────────


def _mask_key(key: str) -> str:
    if not key:
        return ""
    return f"{key[:6]}…{key[-4:]}" if len(key) > 12 else "…"


@app.get("/curate", response_class=HTMLResponse)
def curate(request: Request):
    cfg = llm_config()
    return templates.TemplateResponse(
        request,
        "curate.html",
        _ctx(
            request,
            title="Curation",
            configured=cfg is not None,
            base_url=cfg["base_url"] if cfg else "",
            masked_key=_mask_key(cfg["api_key"]) if cfg else "",
            model=cfg["model"] if cfg else "",
        ),
    )


@app.post("/curate/settings")
def curate_settings(
    base_url: str = Form(...),
    api_key: str = Form(...),
    model: str = Form(...),
):
    if not base_url.strip() or not api_key.strip() or not model.strip():
        raise HTTPException(400, "base URL, API key and model are all required")
    save_llm_config(base_url, api_key, model)
    return RedirectResponse("/curate", status_code=303)


@app.post("/curate/scan")
def curate_scan(
    lang: str = Form("vi"),
    limit: int = Form(20),
):
    lang = lang if lang in LANGUAGES else "vi"
    limit = min(max(int(limit), 1), 200)
    rows = ambiguous_synsets(lang, limit)
    return {"count": len(rows), "rows": rows}


@app.post("/curate/run")
def curate_run(payload: dict = None):
    if payload is None:
        payload = {}
    items = payload.get("items") or []
    langs = payload.get("langs") or ["vi", "zh", "en"]
    if not items:
        raise HTTPException(400, "no synsets selected")
    if llm_config() is None:
        raise HTTPException(400, "LLM is not configured — add API settings first")
    try:
        proposals = run_curation_batch(list(items)[:40], list(langs))
    except Exception as exc:  # noqa: BLE001 - surface LLM errors to the form
        raise HTTPException(502, str(exc)) from exc
    return {"count": len(proposals), "proposals": proposals}


@app.post("/curate/apply")
def curate_apply(payload: dict = None):
    if payload is None:
        payload = {}
    proposals = payload.get("proposals") or []
    if not proposals:
        raise HTTPException(400, "no proposals to apply")
    applied = apply_proposals(proposals)
    return {"applied": applied}


@app.post("/curate/export")
def curate_export():
    """Re-export union + zh-3000 from Postgres (with overrides applied)."""
    export_json(top_n=12000)
    export_json(top_n=3000, pivot="zh")
    return {"ok": True, "msg": "Re-exported out/core_vocabulary.json and out/core_vocabulary.zh-3000.json"}


# ── Jobs (Big-Tech job queue UI) ──────────────────────────────────────────────


def _gloss_job_fn(top_n: int):
    from warehouse.generate_all_glosses import DEFAULT_WORKERS, run as run_glosses

    def fn(ctx) -> None:  # ctx is warehouse.jobs.JobContext
        run_glosses(
            top_n,
            limit=None,
            langs=None,
            workers=DEFAULT_WORKERS,
            log=ctx.log,
            progress=lambda done, total: ctx.progress(done, total),
            cancelled=ctx.cancelled,
        )

    return fn


JOB_KINDS = {
    "gloss-3000": ("Glosses top 3000", lambda: _gloss_job_fn(3000)),
    "gloss-6000": ("Glosses top 6000", lambda: _gloss_job_fn(6000)),
    "gloss-9000": ("Glosses top 9000", lambda: _gloss_job_fn(9000)),
    "gloss-12000": ("Glosses top 12000", lambda: _gloss_job_fn(12000)),
}


@app.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request):
    return templates.TemplateResponse(
        request,
        "jobs.html",
        _ctx(request, title="Jobs", jobs=list_jobs(20), any_running=is_any_running(), kinds=JOB_KINDS),
    )


@app.get("/jobs/api")
def jobs_api():
    return {"jobs": list_jobs(20), "any_running": is_any_running()}


@app.post("/jobs/start")
def jobs_start(kind: str = Form(...)):
    if kind not in JOB_KINDS:
        raise HTTPException(400, f"Unknown job kind: {kind}")
    if is_any_running():
        raise HTTPException(409, "A job is already running.")
    label, factory = JOB_KINDS[kind]
    run_job(label, factory())
    return RedirectResponse("/jobs", status_code=303)


@app.post("/jobs/{job_id}/cancel")
def jobs_cancel(job_id: str):
    if not cancel_job(job_id):
        raise HTTPException(404, "Job not found or already finished")
    return RedirectResponse("/jobs", status_code=303)


def run(host: str = "127.0.0.1", port: int = 8787) -> None:
    import uvicorn

    uvicorn.run("warehouse.web:app", host=host, port=port, reload=False)
