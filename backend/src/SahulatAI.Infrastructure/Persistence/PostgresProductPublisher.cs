using Npgsql;
using SahulatAI.Application.Features.Catalog;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresProductPublisher(CatalogWriterDataSource writer) : IProductPublisher
{
    public async Task<bool> PublishAsync(Guid userId, Guid vendorId, Guid productId,
        CancellationToken cancellationToken)
    {
        const string sql = """
            WITH published AS (
                UPDATE catalog.products p
                SET status = 'published', published_at = now(),
                    updated_by_user_id = @user_id, updated_at = now()
                WHERE p.id = @product_id AND p.vendor_id = @vendor_id AND p.status = 'draft'
                  AND EXISTS (
                      SELECT 1 FROM iam.users u
                      JOIN iam.vendor_memberships m ON m.user_id = u.id
                      JOIN catalog.vendors v ON v.id = m.vendor_id
                      WHERE u.id = @user_id AND m.vendor_id = @vendor_id
                        AND u.status = 'active' AND m.status = 'active' AND v.status = 'active'
                        AND m.role IN ('owner', 'manager')
                  )
                  AND EXISTS (
                      SELECT 1 FROM catalog.categories c
                      WHERE c.id = p.category_id AND c.status = 'active'
                  )
                  AND EXISTS (
                      SELECT 1 FROM catalog.product_images im
                      WHERE im.product_id = p.id AND im.status = 'active'
                        AND im.archived_at IS NULL
                  )
                  AND EXISTS (
                      SELECT 1 FROM catalog.product_variants v
                      WHERE v.product_id = p.id AND v.is_default AND v.status = 'active'
                  )
                  AND EXISTS (
                      SELECT 1 FROM catalog.product_variants v
                      JOIN catalog.listings l ON l.variant_id = v.id
                      WHERE v.product_id = p.id AND v.is_default AND v.status = 'active'
                        AND l.status IN ('draft', 'active')
                        AND l.price IS NOT NULL AND l.currency IS NOT NULL
                        AND l.availability <> 'unknown'
                  )
                RETURNING p.id
            ), activated AS (
                UPDATE catalog.listings l
                SET status = 'active', updated_at = now()
                FROM catalog.product_variants v, published p
                WHERE l.variant_id = v.id AND v.product_id = p.id AND v.status = 'active'
                  AND l.status = 'draft' AND l.price IS NOT NULL AND l.currency IS NOT NULL
                  AND l.availability <> 'unknown'
                RETURNING l.id
            )
            SELECT id FROM published
            """;
        await using var command = writer.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("product_id", productId);
        return await command.ExecuteScalarAsync(cancellationToken) is Guid;
    }
}

public sealed class UnavailableProductPublisher : IProductPublisher
{
    public Task<bool> PublishAsync(Guid userId, Guid vendorId, Guid productId,
        CancellationToken cancellationToken) => throw new CatalogWriteUnavailableException();
}
