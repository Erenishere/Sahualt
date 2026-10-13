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

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE search.product_text_dense_v1 (
    product_id uuid PRIMARY KEY,
    document_schema_version text NOT NULL,
    corpus_sha256 char(64) NOT NULL,
    encoder_id text NOT NULL,
    encoder_revision text NOT NULL,
    embedding vector(3) NOT NULL,
    indexed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_dense_corpus_sha256
        CHECK (corpus_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_dense_encoder_id_not_blank
        CHECK (btrim(encoder_id) <> ''),
    CONSTRAINT ck_dense_encoder_revision_not_blank
        CHECK (btrim(encoder_revision) <> ''),
    CONSTRAINT ck_dense_document_schema_version
        CHECK (btrim(document_schema_version) <> '')
);

CREATE INDEX ix_product_text_dense_v1_corpus_encoder
    ON search.product_text_dense_v1 (corpus_sha256, encoder_id, encoder_revision);

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
