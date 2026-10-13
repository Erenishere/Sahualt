-- Apply after backend commerce migration 005 as the schema owner. Grant this
-- NOLOGIN capability role to a dedicated non-superuser LOGIN outside this file.
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_admin_runtime') THEN
        CREATE ROLE sahulat_admin_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_admin_runtime'
          AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION 'sahulat_admin_runtime has unsafe role attributes';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO sahulat_admin_runtime', current_database());
END $$;

GRANT USAGE ON SCHEMA iam, catalog, audit TO sahulat_admin_runtime;
GRANT SELECT (id, email, display_name, status, created_at),
      UPDATE (status, updated_at, archived_at) ON iam.users TO sahulat_admin_runtime;
GRANT SELECT (user_id, role, status) ON iam.user_roles TO sahulat_admin_runtime;
GRANT SELECT (vendor_id, user_id, role, status), UPDATE (status, updated_at)
      ON iam.vendor_memberships TO sahulat_admin_runtime;
GRANT SELECT (id, display_name, slug, status, created_at),
      UPDATE (status, updated_at, archived_at) ON catalog.vendors TO sahulat_admin_runtime;
GRANT SELECT (id, vendor_id) ON catalog.products TO sahulat_admin_runtime;
GRANT SELECT (id, status) ON catalog.listings TO sahulat_admin_runtime;
GRANT SELECT (id, entity_type, entity_id, action, vendor_id, created_at),
      INSERT ON audit.audit_log TO sahulat_admin_runtime;

COMMIT;
