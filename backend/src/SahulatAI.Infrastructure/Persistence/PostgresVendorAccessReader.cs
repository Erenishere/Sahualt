using Npgsql;
using SahulatAI.Application.Features.Assistant;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresVendorAccessReader(NpgsqlDataSource dataSource) : IVendorAccessReader
{
    public async Task<bool> IsActiveUserAsync(Guid userId, CancellationToken cancellationToken)
    {
        const string sql = "SELECT EXISTS (SELECT 1 FROM iam.users WHERE id = @user_id AND status = 'active')";
        await using var command = dataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        return (bool)(await command.ExecuteScalarAsync(cancellationToken) ?? false);
    }

    public async Task<IReadOnlyList<string>> GetActiveRolesAsync(Guid userId, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT r.role FROM iam.user_roles r JOIN iam.users u ON u.id = r.user_id
            WHERE r.user_id = @user_id AND r.status = 'active' AND u.status = 'active'
            ORDER BY r.role
            """;
        await using var command = dataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var roles = new List<string>();
        while (await reader.ReadAsync(cancellationToken)) roles.Add(reader.GetString(0));
        return roles;
    }

    public async Task<IReadOnlyList<VendorAccess>> GetActiveVendorsAsync(
        Guid userId, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT v.id, v.display_name, m.role
            FROM iam.vendor_memberships m
            JOIN iam.users u ON u.id = m.user_id
            JOIN catalog.vendors v ON v.id = m.vendor_id
            WHERE m.user_id = @user_id AND m.status = 'active'
              AND u.status = 'active' AND v.status = 'active'
            ORDER BY v.display_name, v.id
            LIMIT 100
            """;
        await using var command = dataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var vendors = new List<VendorAccess>();
        while (await reader.ReadAsync(cancellationToken))
            vendors.Add(new VendorAccess(reader.GetGuid(0), reader.GetString(1), reader.GetString(2)));
        return vendors;
    }

    public async Task<bool> HasActiveMembershipAsync(
        Guid userId, Guid vendorId, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT EXISTS (
                SELECT 1
                FROM iam.vendor_memberships m
                JOIN iam.users u ON u.id = m.user_id
                JOIN catalog.vendors v ON v.id = m.vendor_id
                WHERE m.user_id = @user_id AND m.vendor_id = @vendor_id
                  AND m.status = 'active' AND u.status = 'active' AND v.status = 'active'
            )
            """;
        await using var command = dataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        return (bool)(await command.ExecuteScalarAsync(cancellationToken) ?? false);
    }

    public async Task<bool> CanManageCatalogAsync(
        Guid userId, Guid vendorId, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT EXISTS (
                SELECT 1 FROM iam.vendor_memberships m
                JOIN iam.users u ON u.id = m.user_id
                JOIN catalog.vendors v ON v.id = m.vendor_id
                WHERE m.user_id = @user_id AND m.vendor_id = @vendor_id
                  AND m.status = 'active' AND u.status = 'active' AND v.status = 'active'
                  AND m.role IN ('owner', 'manager', 'staff')
            )
            """;
        await using var command = dataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        return (bool)(await command.ExecuteScalarAsync(cancellationToken) ?? false);
    }

    public async Task<bool> CanPublishCatalogAsync(
        Guid userId, Guid vendorId, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT EXISTS (
                SELECT 1 FROM iam.vendor_memberships m
                JOIN iam.users u ON u.id = m.user_id
                JOIN catalog.vendors v ON v.id = m.vendor_id
                WHERE m.user_id = @user_id AND m.vendor_id = @vendor_id
                  AND m.status = 'active' AND u.status = 'active' AND v.status = 'active'
                  AND m.role IN ('owner', 'manager')
            )
            """;
        await using var command = dataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        return (bool)(await command.ExecuteScalarAsync(cancellationToken) ?? false);
    }
}
