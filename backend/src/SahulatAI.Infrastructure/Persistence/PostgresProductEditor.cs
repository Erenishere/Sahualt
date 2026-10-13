using Npgsql;
using NpgsqlTypes;
using SahulatAI.Application.Features.Catalog;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresProductEditor(CatalogWriterDataSource writer) : IProductEditor
{
    public async Task<bool> UpdateProductAsync(Guid userId, Guid vendorId, Guid productId,
        UpdateProductDetails request, CancellationToken cancellationToken)
    {
        const string sql = """
            UPDATE catalog.products p SET name = @name, description = @description,
                category_id = @category_id, updated_by_user_id = @user_id, updated_at = now()
            WHERE p.id = @product_id AND p.vendor_id = @vendor_id
              AND p.status IN ('draft', 'published', 'paused') AND p.archived_at IS NULL
              AND (@category_id IS NULL OR EXISTS (
                  SELECT 1 FROM catalog.categories c WHERE c.id = @category_id AND c.status = 'active'
              ))
              AND EXISTS (
                  SELECT 1 FROM iam.users u JOIN iam.vendor_memberships m ON m.user_id = u.id
                  JOIN catalog.vendors v ON v.id = m.vendor_id
                  WHERE u.id = @user_id AND u.status = 'active' AND m.vendor_id = @vendor_id
                    AND m.status = 'active' AND m.role IN ('owner','manager','staff') AND v.status = 'active'
              ) RETURNING p.id
            """;
        await using var command = writer.DataSource.CreateCommand(sql);
        AddScope(command, userId, vendorId, productId);
        command.Parameters.AddWithValue("name", request.Name);
        command.Parameters.AddWithValue("description", request.Description);
        command.Parameters.Add("category_id", NpgsqlDbType.Uuid).Value = (object?)request.CategoryId ?? DBNull.Value;
        return await command.ExecuteScalarAsync(cancellationToken) is Guid;
    }

    public async Task<bool> UpdateVariantAsync(Guid userId, Guid vendorId, Guid productId, Guid variantId,
        UpdateVariantDetails request, CancellationToken cancellationToken)
    {
        const string sql = """
            UPDATE catalog.product_variants pv SET variant_code = @variant_code, sku = @sku,
                color = @color, size = @size, updated_at = now()
            FROM catalog.products p
            WHERE pv.id = @variant_id AND pv.product_id = p.id AND p.id = @product_id
              AND p.vendor_id = @vendor_id AND pv.status IN ('draft','active','paused')
              AND pv.archived_at IS NULL AND p.status IN ('draft','published','paused')
              AND EXISTS (
                  SELECT 1 FROM iam.users u JOIN iam.vendor_memberships m ON m.user_id = u.id
                  JOIN catalog.vendors v ON v.id = m.vendor_id
                  WHERE u.id = @user_id AND u.status = 'active' AND m.vendor_id = @vendor_id
                    AND m.status = 'active' AND m.role IN ('owner','manager','staff') AND v.status = 'active'
              ) RETURNING pv.id
            """;
        await using var command = writer.DataSource.CreateCommand(sql);
        AddScope(command, userId, vendorId, productId);
        command.Parameters.AddWithValue("variant_id", variantId);
        command.Parameters.AddWithValue("variant_code", request.VariantCode);
        AddNullableText(command, "sku", request.Sku);
        AddNullableText(command, "color", request.Color);
        AddNullableText(command, "size", request.Size);
        return await command.ExecuteScalarAsync(cancellationToken) is Guid;
    }

    public async Task<bool> UpdateListingAsync(Guid userId, Guid vendorId, Guid productId, Guid listingId,
        UpdateListingCommercialDetails request, CancellationToken cancellationToken)
    {
        const string sql = """
            UPDATE catalog.listings l SET price = @price, currency = @currency,
                availability = @availability, allow_customer_offers = @allow_offers, updated_at = now()
            FROM catalog.product_variants pv JOIN catalog.products p ON p.id = pv.product_id
            WHERE l.id = @listing_id AND l.variant_id = pv.id AND p.id = @product_id
              AND p.vendor_id = @vendor_id AND l.status IN ('draft','active','paused')
              AND l.archived_at IS NULL AND pv.status IN ('draft','active','paused')
              AND p.status IN ('draft','published','paused')
              AND EXISTS (
                  SELECT 1 FROM iam.users u JOIN iam.vendor_memberships m ON m.user_id = u.id
                  JOIN catalog.vendors v ON v.id = m.vendor_id
                  WHERE u.id = @user_id AND u.status = 'active' AND m.vendor_id = @vendor_id
                    AND m.status = 'active' AND m.role IN ('owner','manager','staff') AND v.status = 'active'
              ) RETURNING l.id
            """;
        await using var command = writer.DataSource.CreateCommand(sql);
        AddScope(command, userId, vendorId, productId);
        command.Parameters.AddWithValue("listing_id", listingId);
        command.Parameters.AddWithValue("price", request.Price);
        command.Parameters.AddWithValue("currency", request.Currency);
        command.Parameters.AddWithValue("availability", request.Availability);
        command.Parameters.AddWithValue("allow_offers", request.AllowCustomerOffers);
        return await command.ExecuteScalarAsync(cancellationToken) is Guid;
    }

    private static void AddScope(NpgsqlCommand command, Guid userId, Guid vendorId, Guid productId)
    {
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("product_id", productId);
    }
    private static void AddNullableText(NpgsqlCommand command, string name, string? value) =>
        command.Parameters.Add(name, NpgsqlDbType.Text).Value = (object?)value ?? DBNull.Value;
}

public sealed class UnavailableProductEditor : IProductEditor
{
    private static Task<bool> Throw() => Task.FromException<bool>(new CatalogWriteUnavailableException());
    public Task<bool> UpdateProductAsync(Guid a,Guid b,Guid c,UpdateProductDetails d,CancellationToken e)=>Throw();
    public Task<bool> UpdateVariantAsync(Guid a,Guid b,Guid c,Guid d,UpdateVariantDetails e,CancellationToken f)=>Throw();
    public Task<bool> UpdateListingAsync(Guid a,Guid b,Guid c,Guid d,UpdateListingCommercialDetails e,CancellationToken f)=>Throw();
}
