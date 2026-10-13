-- Apply after backend commerce migration 005 as the schema owner.
-- Grant this capability to a dedicated local registration LOGIN.
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_registration_writer') THEN
        CREATE ROLE sahulat_registration_writer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_registration_writer'
          AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION 'sahulat_registration_writer has unsafe role attributes';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO sahulat_registration_writer', current_database());
END $$;

GRANT USAGE ON SCHEMA iam, catalog TO sahulat_registration_writer;
GRANT INSERT (email, email_normalized, password_hash, display_name, status, email_verified_at),
      SELECT (id, email_normalized) ON iam.users TO sahulat_registration_writer;
GRANT INSERT (display_name, slug, status, created_by_user_id),
      SELECT (id) ON catalog.vendors TO sahulat_registration_writer;
GRANT INSERT (vendor_id, user_id, role, status)
      ON iam.vendor_memberships TO sahulat_registration_writer;
GRANT INSERT (user_id, role) ON iam.user_roles TO sahulat_registration_writer;
GRANT INSERT (user_id, phone) ON iam.customer_profiles TO sahulat_registration_writer;

COMMIT;
