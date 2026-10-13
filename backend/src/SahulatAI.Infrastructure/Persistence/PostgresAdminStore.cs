using System.Data;
using System.Text.Json;
using Npgsql;
using NpgsqlTypes;
using SahulatAI.Application.Features.Admin;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class AdminDataSource(NpgsqlDataSource dataSource) : IAsyncDisposable
{
    public NpgsqlDataSource DataSource { get; } = dataSource;
    public ValueTask DisposeAsync() => DataSource.DisposeAsync();
}

public sealed class PostgresAdminStore(AdminDataSource admin) : IAdminStore
{
    public async Task<AdminSummary?> GetSummaryAsync(Guid actorId, CancellationToken cancellationToken)
    {
        const string countsSql = """
            SELECT
              (SELECT count(*)::int FROM catalog.vendors),
              (SELECT count(*)::int FROM catalog.listings WHERE status = 'active'),
              (SELECT count(*)::int FROM iam.users),
              (SELECT count(*)::int FROM catalog.vendors WHERE status = 'pending')
            WHERE EXISTS (
                SELECT 1 FROM iam.users u JOIN iam.user_roles r ON r.user_id = u.id
                WHERE u.id = @actor_id AND u.status = 'active'
                  AND r.role = 'platform_admin' AND r.status = 'active'
            )
            """;
        await using var counts = admin.DataSource.CreateCommand(countsSql);
        counts.Parameters.AddWithValue("actor_id", actorId);
        int vendors;
        int listings;
        int users;
        int pending;
        await using (var reader = await counts.ExecuteReaderAsync(cancellationToken))
        {
            if (!await reader.ReadAsync(cancellationToken)) return null;
            vendors = reader.GetInt32(0);
            listings = reader.GetInt32(1);
            users = reader.GetInt32(2);
            pending = reader.GetInt32(3);
        }

        const string activitySql = """
            SELECT id, entity_type, entity_id, action, vendor_id, created_at
            FROM audit.audit_log
            ORDER BY created_at DESC, id DESC LIMIT 20
            """;
        await using var activity = admin.DataSource.CreateCommand(activitySql);
        await using var activityReader = await activity.ExecuteReaderAsync(cancellationToken);
        var recent = new List<AdminActivityRecord>();
        while (await activityReader.ReadAsync(cancellationToken))
            recent.Add(new AdminActivityRecord(
                activityReader.GetGuid(0), activityReader.GetString(1), activityReader.GetGuid(2),
                activityReader.GetString(3), activityReader.IsDBNull(4) ? null : activityReader.GetGuid(4),
                activityReader.GetFieldValue<DateTimeOffset>(5)));
        return new AdminSummary(vendors, listings, users, pending, recent);
    }

    public async Task<IReadOnlyList<AdminUserRecord>?> GetUsersAsync(Guid actorId, string? status,
        int limit, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT u.id, u.email, u.display_name, u.status, u.created_at,
                   COALESCE(array_agg(r.role ORDER BY r.role) FILTER (WHERE r.status = 'active'), ARRAY[]::text[])
            FROM iam.users u
            LEFT JOIN iam.user_roles r ON r.user_id = u.id
            WHERE (CAST(@status AS text) IS NULL OR u.status = @status)
              AND EXISTS (
                  SELECT 1 FROM iam.users au JOIN iam.user_roles ar ON ar.user_id = au.id
                  WHERE au.id = @actor_id AND au.status = 'active'
                    AND ar.role = 'platform_admin' AND ar.status = 'active'
              )
            GROUP BY u.id ORDER BY u.created_at DESC, u.id DESC LIMIT @limit
            """;
        await using var command = admin.DataSource.CreateCommand(sql);
        AddCommon(command, actorId, status, limit);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var users = new List<AdminUserRecord>();
        while (await reader.ReadAsync(cancellationToken))
            users.Add(new AdminUserRecord(reader.GetGuid(0), reader.GetString(1), reader.GetString(2),
                reader.GetString(3), reader.GetFieldValue<DateTimeOffset>(4), reader.GetFieldValue<string[]>(5)));
        if (users.Count == 0 && !await IsAdminAsync(actorId, cancellationToken)) return null;
        return users;
    }

    public async Task<IReadOnlyList<AdminVendorRecord>?> GetVendorsAsync(Guid actorId, string? status,
        int limit, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT v.id, v.display_name, v.slug, v.status, v.created_at,
                   count(DISTINCT m.user_id) FILTER (WHERE m.status = 'active')::int,
                   count(DISTINCT p.id)::int
            FROM catalog.vendors v
            LEFT JOIN iam.vendor_memberships m ON m.vendor_id = v.id
            LEFT JOIN catalog.products p ON p.vendor_id = v.id
            WHERE (CAST(@status AS text) IS NULL OR v.status = @status)
              AND EXISTS (
                  SELECT 1 FROM iam.users au JOIN iam.user_roles ar ON ar.user_id = au.id
                  WHERE au.id = @actor_id AND au.status = 'active'
                    AND ar.role = 'platform_admin' AND ar.status = 'active'
              )
            GROUP BY v.id ORDER BY v.created_at DESC, v.id DESC LIMIT @limit
            """;
        await using var command = admin.DataSource.CreateCommand(sql);
        AddCommon(command, actorId, status, limit);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var vendors = new List<AdminVendorRecord>();
        while (await reader.ReadAsync(cancellationToken))
            vendors.Add(new AdminVendorRecord(reader.GetGuid(0), reader.GetString(1), reader.GetString(2),
                reader.GetString(3), reader.GetFieldValue<DateTimeOffset>(4), reader.GetInt32(5), reader.GetInt32(6)));
        if (vendors.Count == 0 && !await IsAdminAsync(actorId, cancellationToken)) return null;
        return vendors;
    }

    public async Task<AdminWriteResult> UpdateUserStatusAsync(Guid actorId, Guid userId, string status,
        CancellationToken cancellationToken)
    {
        if (actorId == userId && status != "active") return AdminWriteResult.InvalidTransition;
        const string sql = """
            WITH updated AS (
                UPDATE iam.users u SET status = @status, updated_at = now(),
                    archived_at = CASE WHEN @status = 'archived' THEN now() ELSE NULL END
                WHERE u.id = @user_id AND EXISTS (
                    SELECT 1 FROM iam.users au JOIN iam.user_roles ar ON ar.user_id = au.id
                    WHERE au.id = @actor_id AND au.status = 'active'
                      AND ar.role = 'platform_admin' AND ar.status = 'active'
                ) RETURNING u.id
            )
            INSERT INTO audit.audit_log (actor_user_id, entity_type, entity_id, action, after_data)
            SELECT @actor_id, 'user', id, 'user.status_changed', jsonb_build_object('status', @status)
            FROM updated RETURNING entity_id
            """;
        await using var command = admin.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("actor_id", actorId);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("status", status);
        return await command.ExecuteScalarAsync(cancellationToken) is Guid
            ? AdminWriteResult.Updated : AdminWriteResult.NotFound;
    }

    public async Task<AdminWriteResult> UpdateVendorStatusAsync(Guid actorId, Guid vendorId, string status,
        CancellationToken cancellationToken)
    {
        await using var connection = await admin.DataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.Serializable, cancellationToken);
        const string sql = """
            UPDATE catalog.vendors v SET status = @status, updated_at = now(),
                archived_at = CASE WHEN @status = 'archived' THEN now() ELSE NULL END
            WHERE v.id = @vendor_id AND EXISTS (
                SELECT 1 FROM iam.users au JOIN iam.user_roles ar ON ar.user_id = au.id
                WHERE au.id = @actor_id AND au.status = 'active'
                  AND ar.role = 'platform_admin' AND ar.status = 'active'
            ) RETURNING v.id
            """;
        await using var command = new NpgsqlCommand(sql, connection, transaction);
        command.Parameters.AddWithValue("actor_id", actorId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("status", status);
        if (await command.ExecuteScalarAsync(cancellationToken) is not Guid)
        {
            await transaction.RollbackAsync(cancellationToken);
            return AdminWriteResult.NotFound;
        }
        if (status == "active")
        {
            const string activateSql = """
                UPDATE iam.vendor_memberships SET status = 'active', updated_at = now()
                WHERE vendor_id = @vendor_id AND status = 'pending';
                UPDATE iam.users u SET status = 'active', updated_at = now()
                WHERE u.status = 'pending' AND EXISTS (
                    SELECT 1 FROM iam.vendor_memberships m
                    WHERE m.vendor_id = @vendor_id AND m.user_id = u.id AND m.status = 'active'
                );
                """;
            await using var activate = new NpgsqlCommand(activateSql, connection, transaction);
            activate.Parameters.AddWithValue("vendor_id", vendorId);
            await activate.ExecuteNonQueryAsync(cancellationToken);
        }
        const string auditSql = """
            INSERT INTO audit.audit_log (actor_user_id, vendor_id, entity_type, entity_id, action, after_data)
            VALUES (@actor_id, @vendor_id, 'vendor', @vendor_id, 'vendor.status_changed', @payload::jsonb)
            """;
        await using var audit = new NpgsqlCommand(auditSql, connection, transaction);
        audit.Parameters.AddWithValue("actor_id", actorId);
        audit.Parameters.AddWithValue("vendor_id", vendorId);
        audit.Parameters.AddWithValue("payload", JsonSerializer.Serialize(new { status }));
        await audit.ExecuteNonQueryAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return AdminWriteResult.Updated;
    }

    private async Task<bool> IsAdminAsync(Guid actorId, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT EXISTS (SELECT 1 FROM iam.users u JOIN iam.user_roles r ON r.user_id = u.id
              WHERE u.id = @actor_id AND u.status = 'active' AND r.role = 'platform_admin' AND r.status = 'active')
            """;
        await using var command = admin.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("actor_id", actorId);
        return await command.ExecuteScalarAsync(cancellationToken) is true;
    }

    private static void AddCommon(NpgsqlCommand command, Guid actorId, string? status, int limit)
    {
        command.Parameters.AddWithValue("actor_id", actorId);
        command.Parameters.Add("status", NpgsqlDbType.Text).Value = (object?)status ?? DBNull.Value;
        command.Parameters.AddWithValue("limit", limit);
    }
}

public sealed class UnavailableAdminStore : IAdminStore
{
    private static Task<T> Throw<T>() => Task.FromException<T>(new AdminUnavailableException());
    public Task<AdminSummary?> GetSummaryAsync(Guid a,CancellationToken b)=>Throw<AdminSummary?>();
    public Task<IReadOnlyList<AdminUserRecord>?> GetUsersAsync(Guid a,string? b,int c,CancellationToken d)=>Throw<IReadOnlyList<AdminUserRecord>?>();
    public Task<IReadOnlyList<AdminVendorRecord>?> GetVendorsAsync(Guid a,string? b,int c,CancellationToken d)=>Throw<IReadOnlyList<AdminVendorRecord>?>();
    public Task<AdminWriteResult> UpdateUserStatusAsync(Guid a,Guid b,string c,CancellationToken d)=>Throw<AdminWriteResult>();
    public Task<AdminWriteResult> UpdateVendorStatusAsync(Guid a,Guid b,string c,CancellationToken d)=>Throw<AdminWriteResult>();
}
