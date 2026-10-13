\set ON_ERROR_STOP on

BEGIN;
SET ROLE sahulat_registration_writer;
INSERT INTO iam.users (email, email_normalized, password_hash, display_name, status)
VALUES ('registration-smoke@sahulat-ai.local', 'registration-smoke@sahulat-ai.local',
        '$argon2id$smoke-only', 'Registration Smoke', 'pending')
ON CONFLICT (email_normalized) DO NOTHING
RETURNING id::text AS user_id \gset
\if :{?user_id}
\else
    SELECT 1/0;
\endif
INSERT INTO catalog.vendors (display_name, slug, status, created_by_user_id)
VALUES ('Registration Smoke Vendor', 'registration-smoke-vendor', 'pending', :'user_id'::uuid)
RETURNING id::text AS vendor_id \gset
INSERT INTO iam.vendor_memberships (vendor_id, user_id, role, status)
VALUES (:'vendor_id'::uuid, :'user_id'::uuid, 'owner', 'pending');
WITH duplicate AS (
    INSERT INTO iam.users (email, email_normalized, password_hash, display_name, status)
    VALUES ('registration-smoke@sahulat-ai.local', 'registration-smoke@sahulat-ai.local',
            '$argon2id$smoke-only', 'Duplicate Smoke', 'pending')
    ON CONFLICT (email_normalized) DO NOTHING
    RETURNING id
)
SELECT count(*) = 0 AS duplicate_ignored FROM duplicate \gset
\if :duplicate_ignored
\else
    SELECT 1/0;
\endif
RESET ROLE;

SET ROLE sahulat_registration_writer;
INSERT INTO iam.users (email, email_normalized, password_hash, display_name, status, email_verified_at)
VALUES ('customer-registration-smoke@sahulat-ai.local', 'customer-registration-smoke@sahulat-ai.local',
        '$argon2id$smoke-only', 'Customer Registration Smoke', 'active', now())
RETURNING id::text AS customer_id \gset
INSERT INTO iam.user_roles (user_id, role) VALUES (:'customer_id'::uuid, 'customer');
INSERT INTO iam.customer_profiles (user_id, phone) VALUES (:'customer_id'::uuid, '+920000000000');
RESET ROLE;

SELECT EXISTS (
    SELECT 1 FROM iam.users u
    JOIN iam.vendor_memberships m ON m.user_id = u.id
    JOIN catalog.vendors v ON v.id = m.vendor_id
    WHERE u.id = :'user_id'::uuid AND v.id = :'vendor_id'::uuid
      AND u.status = 'pending' AND u.email_verified_at IS NULL
      AND m.status = 'pending' AND m.role = 'owner' AND v.status = 'pending'
) AS pending_ok \gset
\if :pending_ok
\else
    SELECT 1/0;
\endif
SELECT EXISTS (
    SELECT 1 FROM iam.users u
    JOIN iam.user_roles r ON r.user_id = u.id
    JOIN iam.customer_profiles cp ON cp.user_id = u.id
    WHERE u.id = :'customer_id'::uuid AND u.status = 'active'
      AND u.email_verified_at IS NOT NULL AND r.role = 'customer' AND r.status = 'active'
      AND cp.phone = '+920000000000'
) AS customer_ok \gset
\if :customer_ok
\else
    SELECT 1/0;
\endif
ROLLBACK;
\echo 'Vendor and customer registration writer smoke passed; fixture transaction rolled back.'
