using System.Data;
using Npgsql;
using SahulatAI.Application.Features.Assistant;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresVendorCatalogReader(NpgsqlDataSource dataSource) : IVendorCatalogReader
{
    private const int ProductListingLimit = 50;

    private const string ActiveMembership = """
        EXISTS (
            SELECT 1 FROM iam.vendor_memberships m
            JOIN iam.users u ON u.id = m.user_id
            JOIN catalog.vendors ve ON ve.id = m.vendor_id
            WHERE m.user_id = @user_id AND m.vendor_id = @vendor_id
              AND m.status = 'active' AND u.status = 'active' AND ve.status = 'active'
        )
        """;

    private const string ListingFrom = """
        FROM catalog.listings l
        JOIN catalog.product_variants v ON v.id = l.variant_id
        JOIN catalog.products p ON p.id = v.product_id
        LEFT JOIN inventory.inventory_balances i ON i.listing_id = l.id
        WHERE p.vendor_id = @vendor_id
          AND p.status <> 'archived'
          AND v.status <> 'archived'
        """;

    private const string PublicationSelect = """
        SELECT p.id, p.name, p.status,
               EXISTS (SELECT 1 FROM catalog.categories c
                       WHERE c.id = p.category_id AND c.status = 'active'),
               EXISTS (SELECT 1 FROM catalog.product_images im
                       WHERE im.product_id = p.id AND im.status = 'active'
                         AND im.archived_at IS NULL),
               EXISTS (SELECT 1 FROM catalog.product_variants v
                       WHERE v.product_id = p.id AND v.is_default AND v.status = 'active'),
               EXISTS (SELECT 1 FROM catalog.product_variants v
                       JOIN catalog.listings l ON l.variant_id = v.id
                       WHERE v.product_id = p.id AND v.is_default AND v.status = 'active'
                         AND l.status IN ('draft', 'active')
                         AND l.price IS NOT NULL AND l.currency IS NOT NULL
                         AND l.availability <> 'unknown')
        FROM catalog.products p
        """;

    public async Task<VendorCatalogPage> GetProductsAsync(
        Guid userId, Guid vendorId, Guid? after, int limit, CancellationToken cancellationToken)
    {
        if (limit is < 1 or > 50) throw new ArgumentOutOfRangeException(nameof(limit));
        var sql = $"""
            {PublicationSelect}
            WHERE p.vendor_id = @vendor_id AND p.status <> 'archived'
              AND p.id > @after AND {ActiveMembership}
            ORDER BY p.id LIMIT @limit
            """;
        await using var command = dataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("after", after ?? Guid.Empty);
        command.Parameters.AddWithValue("limit", limit + 1);
        var items = new List<PublicationFacts>(limit + 1);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
            items.Add(ReadPublicationFacts(reader));
        var hasMore = items.Count > limit;
        if (hasMore) items.RemoveAt(items.Count - 1);
        return new VendorCatalogPage(items, hasMore ? items[^1].ProductId : null);
    }

    public async Task<VendorProductDetails?> GetProductDetailsAsync(
        Guid userId, Guid vendorId, Guid productId, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead, cancellationToken);
        var productSql = $"""
            SELECT id, name, description, status, category_id FROM catalog.products
            WHERE id = @product_id AND vendor_id = @vendor_id AND status <> 'archived'
              AND {ActiveMembership}
            """;
        await using var productCommand = new NpgsqlCommand(productSql, connection, transaction);
        productCommand.Parameters.AddWithValue("user_id", userId);
        productCommand.Parameters.AddWithValue("vendor_id", vendorId);
        productCommand.Parameters.AddWithValue("product_id", productId);

        Guid id;
        string name;
        string description;
        string status;
        Guid? categoryId;
        await using (var product = await productCommand.ExecuteReaderAsync(cancellationToken))
        {
            if (!await product.ReadAsync(cancellationToken)) return null;
            id = product.GetGuid(0);
            name = product.GetString(1);
            description = product.GetString(2);
            status = product.GetString(3);
            categoryId = product.IsDBNull(4) ? null : product.GetGuid(4);
        }

        var listingSql = $"""
            SELECT p.id, p.name, l.id, l.status, l.price, l.currency,
                   l.availability, i.on_hand_quantity, COALESCE(i.reserved_quantity, 0)
            {ListingFrom} AND {ActiveMembership}
              AND p.id = @product_id AND l.status <> 'archived'
            ORDER BY l.id LIMIT @limit
            """;
        await using var listingCommand = new NpgsqlCommand(listingSql, connection, transaction);
        listingCommand.Parameters.AddWithValue("user_id", userId);
        listingCommand.Parameters.AddWithValue("vendor_id", vendorId);
        listingCommand.Parameters.AddWithValue("product_id", productId);
        listingCommand.Parameters.AddWithValue("limit", ProductListingLimit + 1);
        var listings = new List<ListingFact>();
        await using (var reader = await listingCommand.ExecuteReaderAsync(cancellationToken))
        {
            while (await reader.ReadAsync(cancellationToken))
            {
                listings.Add(new ListingFact(
                    reader.GetGuid(0), reader.GetString(1), reader.GetGuid(2), reader.GetString(3),
                    reader.IsDBNull(4) ? null : reader.GetDecimal(4),
                    reader.IsDBNull(5) ? null : reader.GetString(5), reader.GetString(6),
                    reader.IsDBNull(7) ? null : reader.GetInt32(7), reader.GetInt32(8)));
            }
        }

        var imageSql = $"""
            SELECT im.id, im.mime_type, im.width, im.height, im.is_primary
            FROM catalog.product_images im
            JOIN catalog.products p ON p.id = im.product_id
            WHERE p.id = @product_id AND p.vendor_id = @vendor_id
              AND p.status <> 'archived' AND im.status = 'active'
              AND im.archived_at IS NULL
              AND {ActiveMembership}
            ORDER BY im.is_primary DESC, im.sort_order, im.id
            LIMIT 20
            """;
        await using var imageCommand = new NpgsqlCommand(imageSql, connection, transaction);
        imageCommand.Parameters.AddWithValue("user_id", userId);
        imageCommand.Parameters.AddWithValue("vendor_id", vendorId);
        imageCommand.Parameters.AddWithValue("product_id", productId);
        var images = new List<ProductImageFact>();
        await using (var reader = await imageCommand.ExecuteReaderAsync(cancellationToken))
        {
            while (await reader.ReadAsync(cancellationToken))
                images.Add(new ProductImageFact(reader.GetGuid(0), reader.GetString(1),
                    reader.IsDBNull(2) ? null : reader.GetInt32(2),
                    reader.IsDBNull(3) ? null : reader.GetInt32(3), reader.GetBoolean(4)));
        }

        await transaction.CommitAsync(cancellationToken);
        return new VendorProductDetails(id, name, description, status,
            listings.Take(ProductListingLimit).ToArray(), listings.Count > ProductListingLimit, categoryId, images);
    }

    public async Task<IReadOnlyList<CatalogCategory>> GetActiveCategoriesAsync(
        Guid userId, Guid vendorId, CancellationToken cancellationToken)
    {
        var sql = $"""
            SELECT c.id, c.name, c.parent_id
            FROM catalog.categories c
            WHERE c.status = 'active' AND {ActiveMembership}
            ORDER BY c.sort_order, c.name, c.id
            LIMIT 200
            """;
        await using var command = dataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        var categories = new List<CatalogCategory>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
            categories.Add(new CatalogCategory(reader.GetGuid(0), reader.GetString(1),
                reader.IsDBNull(2) ? null : reader.GetGuid(2)));
        return categories;
    }

    public async Task<ProductPage> GetDraftProductsAsync(
        Guid userId, Guid vendorId, int limit, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead, cancellationToken);
        var countSql = $"SELECT count(*) FROM catalog.products WHERE vendor_id = @vendor_id AND status = 'draft' AND {ActiveMembership}";
        await using var countCommand = new NpgsqlCommand(countSql, connection, transaction);
        countCommand.Parameters.AddWithValue("user_id", userId);
        countCommand.Parameters.AddWithValue("vendor_id", vendorId);
        var total = Convert.ToInt32(await countCommand.ExecuteScalarAsync(cancellationToken));

        var pageSql = $"""
            SELECT id, name FROM catalog.products
            WHERE vendor_id = @vendor_id AND status = 'draft' AND {ActiveMembership}
            ORDER BY name, id LIMIT @limit
            """;
        await using var pageCommand = new NpgsqlCommand(pageSql, connection, transaction);
        pageCommand.Parameters.AddWithValue("user_id", userId);
        pageCommand.Parameters.AddWithValue("vendor_id", vendorId);
        pageCommand.Parameters.AddWithValue("limit", limit);
        var products = new List<ProductFact>();
        await using (var reader = await pageCommand.ExecuteReaderAsync(cancellationToken))
        {
            while (await reader.ReadAsync(cancellationToken))
                products.Add(new ProductFact(reader.GetGuid(0), reader.GetString(1)));
        }
        await transaction.CommitAsync(cancellationToken);
        return new ProductPage(total, products);
    }

    public async Task<ListingPage> GetListingsAsync(
        Guid userId,
        Guid vendorId,
        CatalogQuestion question,
        Guid? productId,
        int lowStockThreshold,
        int limit,
        CancellationToken cancellationToken)
    {
        var condition = question switch
        {
            CatalogQuestion.ActiveListings => "AND p.status = 'published' AND v.status = 'active' AND l.status = 'active'",
            CatalogQuestion.DraftListings => "AND l.status = 'draft'",
            CatalogQuestion.LowStock => "AND p.status = 'published' AND v.status = 'active' AND l.status = 'active' AND i.on_hand_quantity IS NOT NULL AND i.on_hand_quantity - i.reserved_quantity <= @threshold",
            CatalogQuestion.UnknownStock => "AND p.status = 'published' AND v.status = 'active' AND l.status = 'active' AND i.on_hand_quantity IS NULL",
            CatalogQuestion.ListingDetails => "AND p.id = @product_id AND l.status <> 'archived'",
            _ => throw new ArgumentOutOfRangeException(nameof(question))
        };

        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead, cancellationToken);
        var countSql = $"SELECT count(*) {ListingFrom} AND {ActiveMembership} {condition}";
        await using var countCommand = new NpgsqlCommand(countSql, connection, transaction);
        AddParameters(countCommand, userId, vendorId, productId, lowStockThreshold);
        var total = Convert.ToInt32(await countCommand.ExecuteScalarAsync(cancellationToken));

        var pageSql = $"""
            SELECT p.id, p.name, l.id, l.status, l.price, l.currency,
                   l.availability, i.on_hand_quantity, COALESCE(i.reserved_quantity, 0)
            {ListingFrom} AND {ActiveMembership} {condition}
            ORDER BY p.name, l.id
            LIMIT @limit
            """;
        await using var pageCommand = new NpgsqlCommand(pageSql, connection, transaction);
        AddParameters(pageCommand, userId, vendorId, productId, lowStockThreshold);
        pageCommand.Parameters.AddWithValue("limit", limit);

        var items = new List<ListingFact>();
        await using (var reader = await pageCommand.ExecuteReaderAsync(cancellationToken))
        {
            while (await reader.ReadAsync(cancellationToken))
            {
                items.Add(new ListingFact(
                    reader.GetGuid(0), reader.GetString(1), reader.GetGuid(2), reader.GetString(3),
                    reader.IsDBNull(4) ? null : reader.GetDecimal(4),
                    reader.IsDBNull(5) ? null : reader.GetString(5), reader.GetString(6),
                    reader.IsDBNull(7) ? null : reader.GetInt32(7), reader.GetInt32(8)));
            }
        }

        await transaction.CommitAsync(cancellationToken);
        return new ListingPage(total, items);
    }

    public async Task<PublicationFacts?> GetPublicationFactsAsync(
        Guid userId, Guid vendorId, Guid productId, CancellationToken cancellationToken)
    {
        var sql = $"""
            {PublicationSelect}
            WHERE p.vendor_id = @vendor_id AND p.id = @product_id AND p.status <> 'archived'
              AND {ActiveMembership}
            """;
        await using var command = dataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("product_id", productId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) return null;
        return ReadPublicationFacts(reader);
    }

    private static PublicationFacts ReadPublicationFacts(NpgsqlDataReader reader) =>
        new(reader.GetGuid(0), reader.GetString(1), reader.GetString(2),
            reader.GetBoolean(3), reader.GetBoolean(4), reader.GetBoolean(5), reader.GetBoolean(6));

    private static void AddParameters(NpgsqlCommand command, Guid userId, Guid vendorId, Guid? productId, int threshold)
    {
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("product_id", productId ?? Guid.Empty);
        command.Parameters.AddWithValue("threshold", threshold);
    }
}
