-- Rank per-language headwords for the core vocabulary catalog.
--
-- Selection order per (synset, lang):
--   1. Specificity: prefer the lemma that is a translation of the FEWEST
--      synsets overall (a lemma mapped to 1 synset is a high-confidence
--      translation; a lemma mapped to 15 synsets is a frequent-but-vague
--      word like "keep" and makes a poor headword for any single sense).
--   2. Frequency: within equally specific candidates, pick the more common
--      lemma (higher zipf).
--   3. Deterministic tie-break by lemma id.
-- Function words are excluded entirely (covers particles/pronouns/etc. that
-- would otherwise top the frequency list for every synset they touch).

WITH lemma_span AS (
    SELECT lemma_id, COUNT(DISTINCT synset_id)::int AS synset_count
    FROM core.sense_lemmas
    GROUP BY lemma_id
),
preferred AS (
    SELECT DISTINCT ON (sl.synset_id, l.lang)
        sl.synset_id,
        l.lang,
        l.id AS lemma_id,
        l.zipf,
        l.wordfreq_rank,
        ls.synset_count
    FROM core.sense_lemmas sl
    JOIN core.lemmas l ON l.id = sl.lemma_id
    JOIN lemma_span ls ON ls.lemma_id = l.id
    LEFT JOIN core.function_words fw
        ON fw.lang = l.lang AND fw.normalized = l.normalized
    WHERE fw.normalized IS NULL
    ORDER BY sl.synset_id, l.lang, ls.synset_count ASC, l.zipf DESC NULLS LAST, l.id
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
        ORDER BY p.zipf DESC NULLS LAST, p.synset_id
    ) AS rank,
    p.lemma_id
FROM preferred p
JOIN catalog c ON c.synset_id = p.synset_id;
