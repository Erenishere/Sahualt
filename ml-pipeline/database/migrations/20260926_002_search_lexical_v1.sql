\set ON_ERROR_STOP on

\if :{?migration_id}
\else
  \echo 'migration_id is required'
  \quit 2
\endif

\if :{?migration_checksum}
\else
  \echo 'migration_checksum is required'
  \quit 2
\endif

BEGIN;

SELECT pg_advisory_xact_lock(hashtextextended('sahulat_ai.schema_migrations', 0));

SELECT EXISTS (
    SELECT 1
    FROM integration.schema_migrations
    WHERE migration_id = :'migration_id'
) AS migration_applied \gset

\if :migration_applied
  SELECT checksum = :'migration_checksum' AS migration_checksum_matches
  FROM integration.schema_migrations
  WHERE migration_id = :'migration_id' \gset

  \if :migration_checksum_matches
    \echo 'Migration already applied with matching checksum:' :migration_id
  \else
    \echo 'Migration checksum mismatch:' :migration_id
    ROLLBACK;
    \quit 3
  \endif
\else

CREATE SCHEMA IF NOT EXISTS search;

CREATE TABLE search.product_text_lexical_v1 (
    product_id uuid PRIMARY KEY,
    document_schema_version text NOT NULL,
    corpus_sha256 char(64) NOT NULL,
    searchable_text text NOT NULL,
    document_tsvector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', searchable_text)
    ) STORED,
    indexed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_lexical_searchable_text_not_blank
        CHECK (btrim(searchable_text) <> ''),
    CONSTRAINT ck_lexical_corpus_sha256
        CHECK (corpus_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_lexical_document_schema_version
        CHECK (btrim(document_schema_version) <> '')
);

CREATE INDEX ix_product_text_lexical_v1_tsvector
    ON search.product_text_lexical_v1
    USING GIN (document_tsvector);

CREATE INDEX ix_product_text_lexical_v1_corpus_sha256
    ON search.product_text_lexical_v1 (corpus_sha256);

INSERT INTO integration.schema_migrations (
    migration_id,
    checksum,
    postgres_version
)
VALUES (
    :'migration_id',
    :'migration_checksum',
    current_setting('server_version')
);

\endif

COMMIT;
