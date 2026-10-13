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

DO $$
BEGIN
    IF to_regclass('integration.schema_migrations') IS NULL THEN
        RAISE EXCEPTION 'canonical migration history is missing';
    END IF;
    IF (
        SELECT count(*) FROM integration.schema_migrations
        WHERE migration_id IN (
            '20260910_001_catalog_core_v1',
            '20260926_002_search_lexical_v1',
            '20260926_003_text_dense_prototype_v1'
        )
    ) <> 3 THEN
        RAISE EXCEPTION 'canonical migrations 001/002/003 must be applied before the backend baseline';
    END IF;
END $$;

SELECT EXISTS (
    SELECT 1 FROM integration.schema_migrations WHERE migration_id = :'migration_id'
) AS migration_applied \gset

\if :migration_applied
  SELECT checksum = :'migration_checksum' AS migration_checksum_matches
  FROM integration.schema_migrations WHERE migration_id = :'migration_id' \gset
  \if :migration_checksum_matches
    \echo 'Migration already applied with matching checksum:' :migration_id
  \else
    \echo 'Migration checksum mismatch:' :migration_id
    ROLLBACK;
    \quit 3
  \endif
\else
  -- Intentional no-op baseline. Existing business objects remain owned by
  -- canonical migration 001; future backend migrations start after this row.
  INSERT INTO integration.schema_migrations (
      migration_id, checksum, postgres_version
  ) VALUES (
      :'migration_id', :'migration_checksum', current_setting('server_version')
  );
\endif

COMMIT;
