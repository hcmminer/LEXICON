PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
export PYTHONPATH := .
export DATABASE_URL ?= postgresql:///dictionary?host=/tmp

.PHONY: venv install download migrate ingest-smoke ingest rank export export-zh-3000 validate smoke app

venv:
	python3 -m venv .venv

install: venv
	$(PIP) install -r requirements.txt

download:
	$(PYTHON) -m warehouse.download_sources

migrate:
	$(PYTHON) -m warehouse migrate

ingest-smoke:
	$(PYTHON) -m warehouse ingest --limit 400 --skip-wiktionary --skip-readings

ingest:
	$(PYTHON) -m warehouse ingest

rank:
	$(PYTHON) -m warehouse rank --top-n 12000

export:
	$(PYTHON) -m warehouse export --top-n 12000

export-zh-3000:
	$(PYTHON) -m warehouse export --pivot zh --top-n 3000

app:
	$(PYTHON) -m warehouse app

validate:
	$(PYTHON) validate.py out/core_vocabulary.json --coverage-out out/coverage.json

smoke: migrate ingest-smoke
	$(PYTHON) -m warehouse rank --top-n 200
	$(PYTHON) -m warehouse export --top-n 200
	$(PYTHON) validate.py out/core_vocabulary.json
