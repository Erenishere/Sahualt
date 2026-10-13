using Npgsql;
using NpgsqlTypes;
using SahulatAI.Application.Features.Catalog;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresListingStockWriter(CatalogWriterDataSource writer) : IListingStockWriter
{
    public async Task<StockUpdateResult> SetAsync(Guid userId, Guid vendorId, Guid productId,
        Guid listingId, SetListingStock request, CancellationToken cancellationToken)
    {
        const string sql = """
            WITH authorized AS MATERIALIZED (
                SELECT l.id
                FROM catalog.listings l
                JOIN catalog.product_variants pv ON pv.id = l.variant_id
                JOIN catalog.products p ON p.id = pv.product_id
                JOIN catalog.vendors v ON v.id = p.vendor_id
                JOIN iam.vendor_memberships m ON m.vendor_id = v.id
                JOIN iam.users u ON u.id = m.user_id
                WHERE l.id = @listing_id AND p.id = @product_id AND p.vendor_id = @vendor_id
                  AND p.status IN ('draft', 'published', 'paused')
                  AND pv.status = 'active' AND l.status IN ('draft', 'active', 'paused')
                  AND u.id = @user_id AND u.status = 'active'
                  AND m.status = 'active' AND m.role IN ('owner', 'manager', 'staff')
                  AND v.status = 'active'
                FOR UPDATE OF l
            ), balance AS (
                INSERT INTO inventory.inventory_balances (listing_id, on_hand_quantity)
                SELECT id, @on_hand FROM authorized
                ON CONFLICT (listing_id) DO UPDATE
                SET on_hand_quantity = EXCLUDED.on_hand_quantity, updated_at = now()
                WHERE EXCLUDED.on_hand_quantity IS NULL
                   OR inventory.inventory_balances.reserved_quantity <= EXCLUDED.on_hand_quantity
                RETURNING listing_id
            ), listing AS (
                UPDATE catalog.listings l
                SET availability = @availability, updated_at = now()
                FROM balance b WHERE l.id = b.listing_id
                RETURNING l.id
            )
            SELECT EXISTS (SELECT 1 FROM authorized), EXISTS (SELECT 1 FROM listing)
            """;
        await using var command = writer.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("product_id", productId);
        command.Parameters.AddWithValue("listing_id", listingId);
        command.Parameters.Add("on_hand", NpgsqlDbType.Integer).Value =
            (object?)request.OnHandQuantity ?? DBNull.Value;
        command.Parameters.AddWithValue("availability", request.Availability);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        await reader.ReadAsync(cancellationToken);
        if (!reader.GetBoolean(0)) return StockUpdateResult.ListingNotFound;
        return reader.GetBoolean(1) ? StockUpdateResult.Updated : StockUpdateResult.Conflict;
    }
}

public sealed class UnavailableListingStockWriter : IListingStockWriter
{
    public Task<StockUpdateResult> SetAsync(Guid userId, Guid vendorId, Guid productId,
        Guid listingId, SetListingStock request, CancellationToken cancellationToken) =>
        throw new CatalogWriteUnavailableException();
}
