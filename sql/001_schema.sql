CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.languages (
    code TEXT PRIMARY KEY,
    wordfreq_code TEXT NOT NULL,
    has_wordlist BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS core.sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT,
    license TEXT
);

CREATE TABLE IF NOT EXISTS core.lemmas (
    id BIGSERIAL PRIMARY KEY,
    lang TEXT NOT NULL REFERENCES core.languages (code),
    text TEXT NOT NULL,
    normalized TEXT NOT NULL,
    zipf REAL,
    wordfreq_rank INTEGER,
    UNIQUE (lang, normalized)
);

CREATE INDEX IF NOT EXISTS lemmas_lang_rank_idx
    ON core.lemmas (lang, wordfreq_rank)
    WHERE wordfreq_rank IS NOT NULL;

CREATE TABLE IF NOT EXISTS core.function_words (
    lang TEXT NOT NULL REFERENCES core.languages (code),
    normalized TEXT NOT NULL,
    PRIMARY KEY (lang, normalized)
);

CREATE TABLE IF NOT EXISTS core.synsets (
    id TEXT PRIMARY KEY,
    wn_offset INTEGER NOT NULL,
    pos TEXT NOT NULL,
    definition_en TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS synsets_offset_pos_idx ON core.synsets (wn_offset, pos);

CREATE TABLE IF NOT EXISTS core.sense_lemmas (
    synset_id TEXT NOT NULL REFERENCES core.synsets (id) ON DELETE CASCADE,
    lemma_id BIGINT NOT NULL REFERENCES core.lemmas (id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES core.sources (id),
    PRIMARY KEY (synset_id, lemma_id, source_id)
);

CREATE INDEX IF NOT EXISTS sense_lemmas_lemma_idx ON core.sense_lemmas (lemma_id);
CREATE INDEX IF NOT EXISTS sense_lemmas_synset_idx ON core.sense_lemmas (synset_id);

CREATE TABLE IF NOT EXISTS core.readings (
    lemma_id BIGINT NOT NULL REFERENCES core.lemmas (id) ON DELETE CASCADE,
    system TEXT NOT NULL,
    value TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES core.sources (id),
    PRIMARY KEY (lemma_id, system, source_id)
);

CREATE TABLE IF NOT EXISTS core.concept_ranks (
    synset_id TEXT NOT NULL REFERENCES core.synsets (id) ON DELETE CASCADE,
    lang TEXT NOT NULL REFERENCES core.languages (code),
    rank INTEGER NOT NULL,
    lemma_id BIGINT NOT NULL REFERENCES core.lemmas (id),
    PRIMARY KEY (lang, rank),
    UNIQUE (synset_id, lang)
);

CREATE TABLE IF NOT EXISTS core.ingest_runs (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES core.sources (id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    row_count INTEGER,
    notes TEXT
);

INSERT INTO core.sources (id, name, version, license) VALUES
    ('wordfreq', 'wordfreq', '3.1', 'MIT'),
    ('omw-1.4', 'Open Multilingual Wordnet', '1.4', 'various'),
    ('wordnet', 'Princeton WordNet', '3.1', 'Princeton WordNet License'),
    ('wiktextract', 'Kaikki / wiktextract English dump', 'kaikki', 'CC BY-SA'),
    ('readings', 'Generated readings (pypinyin/kakasi/ipa)', '1', 'generated')
ON CONFLICT (id) DO NOTHING;
