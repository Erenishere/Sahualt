\set ON_ERROR_STOP on

-- Rollback-only platform administration capability smoke. Run after migration 005.
BEGIN;
SELECT uuidv7()::text AS admin_id, uuidv7()::text AS target_user_id,
       uuidv7()::text AS vendor_id \gset
INSERT INTO iam.users (id, email, email_normalized, password_hash, display_name, status, email_verified_at)
VALUES (:'admin_id'::uuid, :'admin_id' || '@example.invalid', :'admin_id' || '@example.invalid',
        '$argon2id$smoke-only', 'Admin Smoke', 'active', now()),
       (:'target_user_id'::uuid, :'target_user_id' || '@example.invalid', :'target_user_id' || '@example.invalid',
        '$argon2id$smoke-only', 'Pending Vendor User', 'pending', now());
INSERT INTO iam.user_roles (user_id, role) VALUES (:'admin_id'::uuid, 'platform_admin');
INSERT INTO catalog.vendors (id, display_name, slug, status, created_by_user_id)
VALUES (:'vendor_id'::uuid, 'Pending Admin Smoke Vendor', 'admin-smoke-' || :'vendor_id',
        'pending', :'target_user_id'::uuid);
INSERT INTO iam.vendor_memberships (vendor_id, user_id, role, status)
VALUES (:'vendor_id'::uuid, :'target_user_id'::uuid, 'owner', 'pending');

SET ROLE sahulat_admin_runtime;
SELECT has_column_privilege(current_user, 'catalog.vendors', 'status', 'UPDATE')
   AND has_column_privilege(current_user, 'iam.users', 'status', 'UPDATE')
   AND NOT has_table_privilege(current_user, 'catalog.vendors', 'INSERT')
   AND NOT has_table_privilege(current_user, 'iam.users', 'DELETE') AS admin_role_limited \gset
\if :admin_role_limited
\else
    SELECT 1/0;
\endif
UPDATE catalog.vendors v SET status = 'active', updated_at = now()
WHERE v.id = :'vendor_id'::uuid AND EXISTS (
    SELECT 1 FROM iam.users u JOIN iam.user_roles r ON r.user_id = u.id
    WHERE u.id = :'admin_id'::uuid AND u.status = 'active'
      AND r.role = 'platform_admin' AND r.status = 'active'
);
UPDATE iam.vendor_memberships SET status = 'active', updated_at = now()
WHERE vendor_id = :'vendor_id'::uuid AND status = 'pending';
UPDATE iam.users SET status = 'active', updated_at = now() WHERE id = :'target_user_id'::uuid;
INSERT INTO audit.audit_log (actor_user_id, vendor_id, entity_type, entity_id, action)
VALUES (:'admin_id'::uuid, :'vendor_id'::uuid, 'vendor', :'vendor_id'::uuid, 'vendor.status_changed');
RESET ROLE;

SELECT EXISTS (
    SELECT 1 FROM catalog.vendors v
    JOIN iam.vendor_memberships m ON m.vendor_id = v.id
    JOIN iam.users u ON u.id = m.user_id
    WHERE v.id = :'vendor_id'::uuid AND v.status = 'active'
      AND m.status = 'active' AND u.status = 'active'
) AS approval_ok \gset
\if :approval_ok
\else
    SELECT 1/0;
\endif
ROLLBACK;
\echo 'Admin capability smoke passed; fixture transaction rolled back.'
