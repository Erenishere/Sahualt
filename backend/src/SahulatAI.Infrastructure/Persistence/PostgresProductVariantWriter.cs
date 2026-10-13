using Npgsql;
using SahulatAI.Application.Features.Catalog;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresProductVariantWriter(CatalogWriterDataSource writer) : IProductVariantWriter
{
    public async Task<CreatedProductVariant?> CreateAsync(
        Guid userId, Guid vendorId, Guid productId, CreateProductVariant request, CancellationToken cancellationToken)
    {
        const string sql = """
            WITH variant AS (
                INSERT INTO catalog.product_variants (product_id, variant_code, status, is_default)
                SELECT p.id, @variant_code, 'active',
                       NOT EXISTS (
                           SELECT 1 FROM catalog.product_variants existing
                           WHERE existing.product_id = p.id AND existing.is_default
                             AND existing.archived_at IS NULL
                       )
                FROM catalog.products p
                JOIN catalog.vendors v ON v.id = p.vendor_id
                JOIN iam.vendor_memberships m ON m.vendor_id = v.id
                JOIN iam.users u ON u.id = m.user_id
                WHERE p.id = @product_id AND p.vendor_id = @vendor_id AND p.status = 'draft'
                  AND u.id = @user_id AND u.status = 'active'
                  AND m.status = 'active' AND m.role IN ('owner', 'manager', 'staff')
                  AND v.status = 'active'
                RETURNING id
            ), listing AS (
                INSERT INTO catalog.listings (
                    variant_id, price, currency, availability, allow_customer_offers, status
                )
                SELECT variant.id, @price, @currency, @availability, @allow_offers, 'draft'
                FROM variant
                RETURNING id, variant_id
            )
            SELECT variant_id, id FROM listing
            """;
        await using var command = writer.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("product_id", productId);
        command.Parameters.AddWithValue("variant_code", request.VariantCode);
        command.Parameters.AddWithValue("price", request.Price);
        command.Parameters.AddWithValue("currency", request.Currency);
        command.Parameters.AddWithValue("availability", request.Availability);
        command.Parameters.AddWithValue("allow_offers", request.AllowCustomerOffers);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken)
            ? new CreatedProductVariant(reader.GetGuid(0), reader.GetGuid(1))
            : null;
    }
}

public sealed class UnavailableProductVariantWriter : IProductVariantWriter
{
    public Task<CreatedProductVariant?> CreateAsync(
        Guid userId, Guid vendorId, Guid productId, CreateProductVariant request, CancellationToken cancellationToken) =>
        throw new CatalogWriteUnavailableException();
}
