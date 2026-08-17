WITH preferred AS (
    SELECT DISTINCT ON (sl.synset_id, l.lang)
        sl.synset_id,
        l.lang,
        l.id AS lemma_id,
        l.zipf,
        l.wordfreq_rank
    FROM core.sense_lemmas sl
    JOIN core.lemmas l ON l.id = sl.lemma_id
    LEFT JOIN core.function_words fw
        ON fw.lang = l.lang AND fw.normalized = l.normalized
    WHERE fw.normalized IS NULL
    ORDER BY sl.synset_id, l.lang, l.zipf DESC NULLS LAST, l.id
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
