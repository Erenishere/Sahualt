\set ON_ERROR_STOP on

BEGIN;
SELECT u.id::text AS user_id, v.id::text AS vendor_id
FROM iam.users u
JOIN iam.vendor_memberships m ON m.user_id = u.id
JOIN catalog.vendors v ON v.id = m.vendor_id AND v.created_by_user_id = u.id
WHERE u.email_normalized = :'registration_email'
  AND u.status = 'pending' AND u.email_verified_at IS NULL
  AND m.status = 'pending' AND m.role = 'owner'
  AND v.status = 'pending'
FOR UPDATE OF u, m, v \gset

\if :{?user_id}
UPDATE iam.users SET status = 'active', email_verified_at = now(), updated_at = now()
WHERE id = :'user_id'::uuid AND status = 'pending';
UPDATE catalog.vendors SET status = 'active', updated_at = now()
WHERE id = :'vendor_id'::uuid AND status = 'pending';
UPDATE iam.vendor_memberships SET status = 'active', updated_at = now()
WHERE user_id = :'user_id'::uuid AND vendor_id = :'vendor_id'::uuid
  AND status = 'pending';
COMMIT;
\echo 'Local pending vendor approved.'
\else
ROLLBACK;
SELECT 1/0;
\endif
