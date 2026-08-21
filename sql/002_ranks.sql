-- Rank per-language headwords for the core vocabulary catalog.
--
-- Selection order per (synset, lang):
--   1. Specificity & Quality Score:
--      - Prefer lemmas with higher Zipf score (populated dynamically for multi-word compounds).
--      - Apply compound bonus for isolating languages (e.g. Vietnamese multi-syllable words)
--        to prevent bound single syllables ('trình', 'phố', 'tiết') from beating full words
--        ('chương trình', 'thành phố', 'thời tiết').
--      - Penalize hyper-polysemous lemmas (high synset count).
--   2. Deterministic tie-break by lemma id.
-- Function words are excluded entirely.

WITH lemma_span AS (
    SELECT lemma_id, COUNT(DISTINCT synset_id)::int AS synset_count
    FROM core.sense_lemmas
    GROUP BY lemma_id
),
scored AS (
    SELECT
        sl.synset_id,
        l.lang,
        l.id AS lemma_id,
        l.zipf,
        l.wordfreq_rank,
        ls.synset_count,
        (
            COALESCE(l.zipf, 0.0)
            + CASE
                WHEN sl.synset_id LIKE l.normalized || '.%%' THEN 1.0
                ELSE 0.0
              END
            + CASE
                WHEN l.lang = 'vi' AND POSITION(' ' IN l.text) > 0 THEN 0.6
                WHEN l.lang IN ('zh', 'ja', 'ko') AND char_length(btrim(l.text)) >= 2 THEN 0.5
                ELSE 0.0
              END
            - CASE
                WHEN l.lang IN ('zh', 'ja') AND char_length(btrim(l.text)) = 1 THEN 0.8
                ELSE 0.0
              END
            - (ls.synset_count * 0.02)
        ) AS selection_score
    FROM core.sense_lemmas sl
    JOIN core.lemmas l ON l.id = sl.lemma_id
    JOIN lemma_span ls ON ls.lemma_id = l.id
    LEFT JOIN core.function_words fw
        ON fw.lang = l.lang AND fw.normalized = l.normalized
    WHERE fw.normalized IS NULL
      AND l.text NOT LIKE '-%%'
      AND l.text NOT LIKE '%%-'
      AND POSITION('.' IN l.text) = 0
),
preferred AS (
    SELECT DISTINCT ON (s.synset_id, s.lang)
        s.synset_id,
        s.lang,
        s.lemma_id,
        s.zipf,
        s.wordfreq_rank,
        s.synset_count,
        s.selection_score
    FROM scored s
    ORDER BY s.synset_id, s.lang, s.selection_score DESC, s.synset_count ASC, s.lemma_id
),
seeded AS (
    SELECT DISTINCT synset_id
    FROM preferred
    WHERE wordfreq_rank IS NOT NULL
      AND wordfreq_rank <= %(top_n)s
),
catalog AS (
    SELECT p.synset_id
    FROM preferred p
    JOIN seeded s ON s.synset_id = p.synset_id
    GROUP BY p.synset_id
    HAVING BOOL_OR(p.lang = 'en') AND COUNT(*) >= 2
)
INSERT INTO core.concept_ranks (synset_id, lang, rank, lemma_id)
SELECT
    p.synset_id,
    p.lang,
    ROW_NUMBER() OVER (
        PARTITION BY p.lang
        ORDER BY
            COALESCE(p.wordfreq_rank, 999999) ASC,
            p.selection_score DESC,
            p.zipf DESC NULLS LAST,
            p.synset_id
    ) AS rank,
    p.lemma_id
FROM preferred p
JOIN catalog c ON c.synset_id = p.synset_id;

