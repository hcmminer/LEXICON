# B2B Dictionary Console — Design

Free local web console over the Postgres warehouse. No auth, no API keys.

## Audience

Data teams and product teams who want to browse the multilingual catalog and export pivot packs (default: Chinese 3000 + 34 translations).

## Architecture

```
Browser → FastAPI 127.0.0.1:8787 → Jinja + static CSS
                ↓
         warehouse.db (Postgres)
                ↓
         rank / export_json (existing)
```

`make app` starts uvicorn. Bind localhost only.

## Routes

| Path | Job |
|---|---|
| `GET /` | Coverage dashboard |
| `GET /catalog` | Search + pivot/rank filters |
| `GET /catalog/{synset_id}` | 35-language term sheet + phonology slots |
| `GET /export` | Form → download pivot JSON/gz |
| `POST /export` | Stream file |
| `GET /ops` | Ingest / rank / export-to-disk controls |
| `POST /ops/run` | Start one job (localhost only) |

## Export contract

- `pivot` + `topN` (default `zh`, `3000`)
- Envelope: `pivot`, `topN`, `count`, `phonology`, `concepts[]`
- Every concept has `terms[pivot]`
- Other langs omitted when missing
- Pivot ranks 1..N contiguous

## Ops

Safe: rank, export-to-disk. Ingest steps available with explicit confirm. One job at a time. Logs on `/ops`.

## Out of scope

Auth, billing, hosted SaaS, React, API keys, public bind.
