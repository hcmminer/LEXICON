PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
export PYTHONPATH := .
export DATABASE_URL ?= postgresql:///dictionary?host=/tmp

.PHONY: venv install migrate ingest-smoke ingest rank export validate smoke

venv:
	python3 -m venv .venv

install: venv
	$(PIP) install -r requirements.txt

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

validate:
	$(PYTHON) validate.py out/core_vocabulary.json --coverage-out out/coverage.json

smoke: migrate ingest-smoke
	$(PYTHON) -m warehouse rank --top-n 200
	$(PYTHON) -m warehouse export --top-n 200
	$(PYTHON) validate.py out/core_vocabulary.json
