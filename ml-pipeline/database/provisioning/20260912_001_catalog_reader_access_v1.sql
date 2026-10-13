\set ON_ERROR_STOP on

-- Password verifier is supplied through private stdin, never a committed value or CLI argument.
BEGIN;
SET LOCAL log_statement = 'none';
SET LOCAL log_min_duration_statement = -1;
SET LOCAL log_min_duration_sample = -1;
SET LOCAL log_min_error_statement = 'panic';
SELECT pg_advisory_xact_lock(hashtextextended('sahulat_ai.schema_migrations', 0));

SELECT 1 / CASE WHEN EXISTS (
    SELECT 1 FROM integration.schema_migrations
    WHERE migration_id = '20260910_001_catalog_core_v1'
) THEN 1 ELSE 0 END;

SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'reader_role') AS reader_exists \gset
SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'reader_role') AS reader_created \gset
\if :reader_exists
    -- Existing unsafe roles are rejected, not silently stripped of privileges or rotated.
    SELECT 1 / CASE WHEN EXISTS (
        SELECT 1 FROM pg_roles r WHERE r.rolname = :'reader_role' AND r.rolcanlogin
          AND NOT (r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication
                   OR r.rolbypassrls OR r.rolinherit)
          AND NOT EXISTS (SELECT 1 FROM pg_auth_members WHERE member = r.oid)
          AND NOT EXISTS (SELECT 1 FROM pg_class WHERE relowner = r.oid)
          AND NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspowner = r.oid)
          AND NOT EXISTS (SELECT 1 FROM pg_database WHERE datdba = r.oid)
          AND NOT has_database_privilege(r.oid, current_database(), 'CREATE')
          AND NOT EXISTS (
              SELECT 1 FROM pg_namespace n WHERE n.nspname IN
                  ('iam','catalog','inventory','integration','audit','public')
                  AND has_schema_privilege(r.oid, n.oid, 'CREATE'))
          AND NOT EXISTS (
              SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE n.nspname IN ('iam','catalog','inventory','integration','audit','public')
                AND c.relkind IN ('r','p','v','m','f') AND (
                  has_table_privilege(r.oid, c.oid,
                      'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                  OR has_any_column_privilege(r.oid, c.oid, 'INSERT,UPDATE,REFERENCES')
                  OR ((n.nspname <> 'catalog' OR c.relname <> 'visual_product_resolution_v1')
                      AND has_any_column_privilege(r.oid, c.oid, 'SELECT'))))
    ) THEN 1 ELSE 0 END;
\else
    SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
        'NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 4', :'reader_role') \gexec
\endif

SELECT EXISTS (SELECT 1 FROM integration.schema_migrations
    WHERE migration_id = :'migration_id') AS access_applied \gset
\if :access_applied
    SELECT 1 / CASE WHEN checksum = :'migration_checksum' THEN 1 ELSE 0 END
    FROM integration.schema_migrations WHERE migration_id = :'migration_id';
\else
    -- Owner-rights, non-updatable join view: no underlying table privileges for the reader.
    CREATE VIEW catalog.visual_product_resolution_v1
    WITH (security_barrier = true, security_invoker = false) AS
    SELECT product_ref.source_system, product_ref.external_product_id,
        image_ref.external_image_id, product.id AS product_id, image.id AS image_id,
        product.name, product.description,
        (product.archived_at IS NOT NULL OR product.status = 'archived'
         OR image.archived_at IS NOT NULL OR image.status = 'archived') AS blocked
    FROM catalog.product_external_refs product_ref
    JOIN catalog.products product ON product.id = product_ref.product_id
    JOIN catalog.product_images image ON image.product_id = product.id
    JOIN catalog.image_external_refs image_ref ON image_ref.image_id = image.id
        AND image_ref.source_system = product_ref.source_system;
    REVOKE ALL PRIVILEGES ON catalog.visual_product_resolution_v1 FROM PUBLIC;
    INSERT INTO integration.schema_migrations (migration_id, checksum, postgres_version)
    VALUES (:'migration_id', :'migration_checksum', current_setting('server_version'));
\endif

-- A per-role REVOKE cannot negate inherited PUBLIC TEMP. Only this target DB is hardened.
SELECT format('REVOKE CREATE, TEMPORARY ON DATABASE %I FROM PUBLIC', current_database()) \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'reader_role') \gexec
GRANT USAGE ON SCHEMA catalog TO :"reader_role";
GRANT SELECT ON catalog.visual_product_resolution_v1 TO :"reader_role";
ALTER ROLE :"reader_role" SET default_transaction_read_only = on;
ALTER ROLE :"reader_role" SET search_path = pg_catalog;

\if :reader_created
    ALTER ROLE :"reader_role" PASSWORD :'reader_password_verifier';
\endif
COMMIT;
