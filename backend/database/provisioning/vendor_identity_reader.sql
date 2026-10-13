-- Apply after catalog-core migration 001, as the database schema owner.
-- Provision a separate non-superuser LOGIN and grant it this role outside this file.
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_identity_reader') THEN
        CREATE ROLE sahulat_identity_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'sahulat_identity_reader'
          AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION 'sahulat_identity_reader has unsafe role attributes';
    END IF;

    EXECUTE format('GRANT CONNECT ON DATABASE %I TO sahulat_identity_reader', current_database());
END $$;

GRANT USAGE ON SCHEMA iam TO sahulat_identity_reader;
GRANT SELECT (id, email_normalized, password_hash, status, email_verified_at)
    ON iam.users TO sahulat_identity_reader;

COMMIT;
