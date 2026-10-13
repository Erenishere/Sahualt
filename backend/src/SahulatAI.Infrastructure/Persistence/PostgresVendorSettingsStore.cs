using Npgsql;
using NpgsqlTypes;
using SahulatAI.Application.Features.Marketplace;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresVendorSettingsStore(CommerceDataSource commerce) : IVendorSettingsStore
{
    public async Task<VendorStoreProfile?> GetAsync(Guid userId, Guid vendorId,
        CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT v.id, v.display_name, v.slug, v.description, v.allow_customer_offers
            FROM catalog.vendors v
            JOIN iam.vendor_memberships m ON m.vendor_id = v.id
            JOIN iam.users u ON u.id = m.user_id
            WHERE v.id = @vendor_id AND v.status = 'active' AND m.user_id = @user_id
              AND m.status = 'active' AND u.status = 'active'
            """;
        await using var command = commerce.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken)
            ? new VendorStoreProfile(reader.GetGuid(0), reader.GetString(1), reader.GetString(2),
                reader.IsDBNull(3) ? null : reader.GetString(3), reader.GetBoolean(4))
            : null;
    }

    public async Task<CommerceWriteResult> UpdateAsync(Guid userId, Guid vendorId,
        UpdateVendorStoreProfile profile, CancellationToken cancellationToken)
    {
        const string sql = """
            WITH updated AS (
                UPDATE catalog.vendors v SET display_name = @display_name,
                    description = @description, allow_customer_offers = @allow_offers,
                    updated_at = now()
                WHERE v.id = @vendor_id AND v.status = 'active' AND EXISTS (
                    SELECT 1 FROM iam.users u JOIN iam.vendor_memberships m ON m.user_id = u.id
                    WHERE u.id = @user_id AND u.status = 'active' AND m.vendor_id = v.id
                      AND m.status = 'active' AND m.role IN ('owner', 'manager')
                ) RETURNING v.id
            )
            INSERT INTO audit.audit_log (actor_user_id, vendor_id, entity_type, entity_id, action, after_data)
            SELECT @user_id, @vendor_id, 'vendor', id, 'vendor.settings_updated',
                   jsonb_build_object('allowCustomerOffers', @allow_offers)
            FROM updated RETURNING entity_id
            """;
        await using var command = commerce.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("display_name", profile.DisplayName);
        command.Parameters.Add("description", NpgsqlDbType.Text).Value =
            (object?)profile.Description ?? DBNull.Value;
        command.Parameters.AddWithValue("allow_offers", profile.AllowCustomerOffers);
        return await command.ExecuteScalarAsync(cancellationToken) is Guid
            ? CommerceWriteResult.Updated : CommerceWriteResult.NotFound;
    }
}

public sealed class UnavailableVendorSettingsStore : IVendorSettingsStore
{
    public Task<VendorStoreProfile?> GetAsync(Guid userId, Guid vendorId,
        CancellationToken cancellationToken) => Task.FromException<VendorStoreProfile?>(new CommerceUnavailableException());
    public Task<CommerceWriteResult> UpdateAsync(Guid userId, Guid vendorId,
        UpdateVendorStoreProfile profile, CancellationToken cancellationToken) =>
        Task.FromException<CommerceWriteResult>(new CommerceUnavailableException());
}
