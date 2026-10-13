using Npgsql;
using SahulatAI.Application.Features.Catalog;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresProductCategoryWriter(CatalogWriterDataSource writer) : IProductCategoryWriter
{
    public async Task<bool> SetAsync(Guid userId, Guid vendorId, Guid productId, Guid categoryId,
        CancellationToken cancellationToken)
    {
        const string sql = """
            UPDATE catalog.products p
            SET category_id = @category_id, updated_by_user_id = @user_id, updated_at = now()
            WHERE p.id = @product_id AND p.vendor_id = @vendor_id AND p.status = 'draft'
              AND EXISTS (
                  SELECT 1 FROM catalog.categories c
                  WHERE c.id = @category_id AND c.status = 'active'
              )
              AND EXISTS (
                  SELECT 1 FROM iam.users u
                  JOIN iam.vendor_memberships m ON m.user_id = u.id
                  JOIN catalog.vendors v ON v.id = m.vendor_id
                  WHERE u.id = @user_id AND m.vendor_id = @vendor_id
                    AND u.status = 'active' AND m.status = 'active' AND v.status = 'active'
                    AND m.role IN ('owner', 'manager', 'staff')
              )
            """;
        await using var command = writer.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("product_id", productId);
        command.Parameters.AddWithValue("category_id", categoryId);
        return await command.ExecuteNonQueryAsync(cancellationToken) == 1;
    }
}

public sealed class UnavailableProductCategoryWriter : IProductCategoryWriter
{
    public Task<bool> SetAsync(Guid userId, Guid vendorId, Guid productId, Guid categoryId,
        CancellationToken cancellationToken) => throw new CatalogWriteUnavailableException();
}
