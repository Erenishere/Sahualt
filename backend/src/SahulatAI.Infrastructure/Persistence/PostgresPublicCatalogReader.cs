using Amazon.S3;
using Npgsql;
using SahulatAI.Application.Features.Catalog;
using SahulatAI.Application.Features.Marketplace;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresPublicCatalogReader(
    NpgsqlDataSource reader,
    IProductImageObjectStore? imageStore) : IPublicCatalogReader
{
    public async Task<PublicProductPage> SearchAsync(string? query, string? category,
        string? vendorSlug, Guid? after, int limit, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT p.id, p.name, v.id, v.display_name, v.slug, c.name,
                   priced.price, priced.currency, priced.availability,
                   CASE WHEN priced.on_hand_quantity IS NULL THEN NULL
                        ELSE priced.on_hand_quantity - priced.reserved_quantity END,
                   v.allow_customer_offers AND priced.allow_customer_offers,
                   image.id
            FROM catalog.products p
            JOIN catalog.vendors v ON v.id = p.vendor_id
            LEFT JOIN catalog.categories c ON c.id = p.category_id AND c.status = 'active'
            JOIN LATERAL (
                SELECT l.price, l.currency, l.availability, l.allow_customer_offers,
                       i.on_hand_quantity, COALESCE(i.reserved_quantity, 0) AS reserved_quantity
                FROM catalog.product_variants pv
                JOIN catalog.listings l ON l.variant_id = pv.id
                LEFT JOIN inventory.inventory_balances i ON i.listing_id = l.id
                WHERE pv.product_id = p.id AND pv.status = 'active'
                  AND l.status = 'active' AND l.price IS NOT NULL AND l.currency IS NOT NULL
                  AND l.availability IN ('in_stock', 'preorder', 'unavailable')
                ORDER BY l.price, l.id
                LIMIT 1
            ) priced ON true
            LEFT JOIN LATERAL (
                SELECT pi.id FROM catalog.product_images pi
                WHERE pi.product_id = p.id AND pi.status = 'active' AND pi.archived_at IS NULL
                ORDER BY pi.is_primary DESC, pi.sort_order, pi.id LIMIT 1
            ) image ON true
            WHERE p.status = 'published' AND p.archived_at IS NULL AND v.status = 'active'
              AND (@after::uuid IS NULL OR p.id > @after)
              AND (@query::text IS NULL OR p.name ILIKE '%' || @query || '%'
                   OR p.description ILIKE '%' || @query || '%'
                   OR v.display_name ILIKE '%' || @query || '%')
              AND (@category::text IS NULL OR lower(c.name) = lower(@category))
              AND (@vendor_slug::text IS NULL OR v.slug = @vendor_slug)
            ORDER BY p.id
            LIMIT @limit_plus_one
            """;
        await using var command = reader.CreateCommand(sql);
        command.Parameters.AddWithValue("after", (object?)after ?? DBNull.Value);
        command.Parameters.AddWithValue("query", (object?)NullIfBlank(query) ?? DBNull.Value);
        command.Parameters.AddWithValue("category", (object?)NullIfBlank(category) ?? DBNull.Value);
        command.Parameters.AddWithValue("vendor_slug", (object?)NullIfBlank(vendorSlug) ?? DBNull.Value);
        command.Parameters.AddWithValue("limit_plus_one", limit + 1);
        await using var result = await command.ExecuteReaderAsync(cancellationToken);
        var products = new List<PublicProductSummary>();
        while (await result.ReadAsync(cancellationToken))
            products.Add(new PublicProductSummary(
                result.GetGuid(0), result.GetString(1), result.GetGuid(2), result.GetString(3),
                result.GetString(4), result.IsDBNull(5) ? null : result.GetString(5),
                result.GetDecimal(6), result.GetString(7), result.GetString(8),
                result.IsDBNull(9) ? null : result.GetInt32(9), result.GetBoolean(10),
                result.IsDBNull(11) ? null : result.GetGuid(11)));
        var hasMore = products.Count > limit;
        if (hasMore) products.RemoveAt(products.Count - 1);
        return new PublicProductPage(products, hasMore ? products[^1].ProductId : null);
    }

    public async Task<IReadOnlyList<PublicProductSummary>> ListSummariesByProductIdsAsync(
        IReadOnlyList<Guid> productIds, CancellationToken cancellationToken)
    {
        if (productIds.Count == 0) return [];
        const string sql = """
            SELECT p.id, p.name, v.id, v.display_name, v.slug, c.name,
                   priced.price, priced.currency, priced.availability,
                   CASE WHEN priced.on_hand_quantity IS NULL THEN NULL
                        ELSE priced.on_hand_quantity - priced.reserved_quantity END,
                   v.allow_customer_offers AND priced.allow_customer_offers,
                   image.id,
                   array_position(@product_ids::uuid[], p.id) AS ord
            FROM catalog.products p
            JOIN catalog.vendors v ON v.id = p.vendor_id
            LEFT JOIN catalog.categories c ON c.id = p.category_id AND c.status = 'active'
            JOIN LATERAL (
                SELECT l.price, l.currency, l.availability, l.allow_customer_offers,
                       i.on_hand_quantity, COALESCE(i.reserved_quantity, 0) AS reserved_quantity
                FROM catalog.product_variants pv
                JOIN catalog.listings l ON l.variant_id = pv.id
                LEFT JOIN inventory.inventory_balances i ON i.listing_id = l.id
                WHERE pv.product_id = p.id AND pv.status = 'active'
                  AND l.status = 'active' AND l.price IS NOT NULL AND l.currency IS NOT NULL
                  AND l.availability IN ('in_stock', 'preorder', 'unavailable')
                ORDER BY l.price, l.id
                LIMIT 1
            ) priced ON true
            LEFT JOIN LATERAL (
                SELECT pi.id FROM catalog.product_images pi
                WHERE pi.product_id = p.id AND pi.status = 'active' AND pi.archived_at IS NULL
                ORDER BY pi.is_primary DESC, pi.sort_order, pi.id LIMIT 1
            ) image ON true
            WHERE p.id = ANY(@product_ids)
              AND p.status = 'published' AND p.archived_at IS NULL AND v.status = 'active'
            ORDER BY ord
            """;
        await using var command = reader.CreateCommand(sql);
        command.Parameters.AddWithValue("product_ids", productIds.ToArray());
        await using var result = await command.ExecuteReaderAsync(cancellationToken);
        var products = new List<PublicProductSummary>();
        while (await result.ReadAsync(cancellationToken))
            products.Add(new PublicProductSummary(
                result.GetGuid(0), result.GetString(1), result.GetGuid(2), result.GetString(3),
                result.GetString(4), result.IsDBNull(5) ? null : result.GetString(5),
                result.GetDecimal(6), result.GetString(7), result.GetString(8),
                result.IsDBNull(9) ? null : result.GetInt32(9), result.GetBoolean(10),
                result.IsDBNull(11) ? null : result.GetGuid(11)));
        return products;
    }

    public async Task<PublicProductDetails?> GetAsync(Guid productId,
        CancellationToken cancellationToken)
    {
        const string productSql = """
            SELECT p.id, p.name, p.description, v.id, v.display_name, v.slug,
                   v.description, v.allow_customer_offers, c.name, image.id
            FROM catalog.products p
            JOIN catalog.vendors v ON v.id = p.vendor_id
            LEFT JOIN catalog.categories c ON c.id = p.category_id AND c.status = 'active'
            LEFT JOIN LATERAL (
                SELECT pi.id FROM catalog.product_images pi
                WHERE pi.product_id = p.id AND pi.status = 'active' AND pi.archived_at IS NULL
                ORDER BY pi.is_primary DESC, pi.sort_order, pi.id LIMIT 1
            ) image ON true
            WHERE p.id = @product_id AND p.status = 'published' AND p.archived_at IS NULL
              AND v.status = 'active'
              AND EXISTS (
                  SELECT 1 FROM catalog.product_variants pv
                  JOIN catalog.listings l ON l.variant_id = pv.id
                  WHERE pv.product_id = p.id AND pv.status = 'active' AND l.status = 'active'
                    AND l.price IS NOT NULL AND l.currency IS NOT NULL
                    AND l.availability IN ('in_stock', 'preorder', 'unavailable')
              )
            """;
        await using var command = reader.CreateCommand(productSql);
        command.Parameters.AddWithValue("product_id", productId);
        Guid vendorId;
        string name;
        string description;
        string vendorName;
        string vendorSlug;
        string? vendorDescription;
        bool vendorAllowsOffers;
        string? category;
        Guid? imageId;
        await using (var result = await command.ExecuteReaderAsync(cancellationToken))
        {
            if (!await result.ReadAsync(cancellationToken)) return null;
            name = result.GetString(1);
            description = result.GetString(2);
            vendorId = result.GetGuid(3);
            vendorName = result.GetString(4);
            vendorSlug = result.GetString(5);
            vendorDescription = result.IsDBNull(6) ? null : result.GetString(6);
            vendorAllowsOffers = result.GetBoolean(7);
            category = result.IsDBNull(8) ? null : result.GetString(8);
            imageId = result.IsDBNull(9) ? null : result.GetGuid(9);
        }

        const string listingsSql = """
            SELECT l.id, pv.id, pv.variant_code, pv.sku, pv.color, pv.size,
                   l.price, l.currency, l.availability,
                   CASE WHEN i.on_hand_quantity IS NULL THEN NULL
                        ELSE i.on_hand_quantity - i.reserved_quantity END,
                   l.allow_customer_offers
            FROM catalog.product_variants pv
            JOIN catalog.listings l ON l.variant_id = pv.id
            LEFT JOIN inventory.inventory_balances i ON i.listing_id = l.id
            WHERE pv.product_id = @product_id AND pv.status = 'active' AND l.status = 'active'
              AND l.price IS NOT NULL AND l.currency IS NOT NULL
              AND l.availability IN ('in_stock', 'preorder', 'unavailable')
            ORDER BY pv.is_default DESC, l.price, l.id LIMIT 100
            """;
        await using var listingsCommand = reader.CreateCommand(listingsSql);
        listingsCommand.Parameters.AddWithValue("product_id", productId);
        await using var listingsResult = await listingsCommand.ExecuteReaderAsync(cancellationToken);
        var listings = new List<PublicListing>();
        while (await listingsResult.ReadAsync(cancellationToken))
            listings.Add(new PublicListing(
                listingsResult.GetGuid(0), listingsResult.GetGuid(1), listingsResult.GetString(2),
                listingsResult.IsDBNull(3) ? null : listingsResult.GetString(3),
                listingsResult.IsDBNull(4) ? null : listingsResult.GetString(4),
                listingsResult.IsDBNull(5) ? null : listingsResult.GetString(5),
                listingsResult.GetDecimal(6), listingsResult.GetString(7), listingsResult.GetString(8),
                listingsResult.IsDBNull(9) ? null : listingsResult.GetInt32(9),
                vendorAllowsOffers && listingsResult.GetBoolean(10)));
        return new PublicProductDetails(productId, name, description, vendorId, vendorName,
            vendorSlug, vendorDescription, category, imageId, listings);
    }

    public async Task<ProductImageContent?> GetImageAsync(Guid productId, Guid imageId,
        CancellationToken cancellationToken)
    {
        if (imageStore is null) return null;
        const string sql = """
            SELECT pi.storage_key, pi.mime_type
            FROM catalog.product_images pi
            JOIN catalog.products p ON p.id = pi.product_id
            JOIN catalog.vendors v ON v.id = p.vendor_id
            WHERE pi.id = @image_id AND pi.product_id = @product_id
              AND pi.status = 'active' AND pi.archived_at IS NULL
              AND p.status = 'published' AND p.archived_at IS NULL AND v.status = 'active'
            """;
        await using var command = reader.CreateCommand(sql);
        command.Parameters.AddWithValue("product_id", productId);
        command.Parameters.AddWithValue("image_id", imageId);
        string key;
        string mimeType;
        await using (var result = await command.ExecuteReaderAsync(cancellationToken))
        {
            if (!await result.ReadAsync(cancellationToken)) return null;
            key = result.GetString(0);
            mimeType = result.GetString(1);
        }
        try { return new ProductImageContent(await imageStore.GetAsync(key, cancellationToken), mimeType); }
        catch (AmazonS3Exception error) when (error.StatusCode == System.Net.HttpStatusCode.NotFound)
        {
            return null;
        }
        catch (FileNotFoundException)
        {
            return null;
        }
    }

    private static string? NullIfBlank(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
