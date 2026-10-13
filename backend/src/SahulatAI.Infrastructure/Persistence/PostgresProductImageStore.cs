using System.Security.Cryptography;
using Amazon.S3;
using Microsoft.Extensions.Logging;
using Npgsql;
using SahulatAI.Application.Features.Catalog;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresProductImageWriter(
    CatalogWriterDataSource writer,
    IProductImageObjectStore store,
    ILogger<PostgresProductImageWriter> logger) : IProductImageWriter
{
    public async Task<UploadedProductImage?> UploadAsync(Guid userId, Guid vendorId, Guid productId,
        byte[] bytes, string mimeType, int width, int height, CancellationToken cancellationToken)
    {
        const string preflightSql = """
            SELECT EXISTS (
                SELECT 1 FROM catalog.products p
                JOIN catalog.vendors v ON v.id = p.vendor_id
                JOIN iam.vendor_memberships m ON m.vendor_id = v.id
                JOIN iam.users u ON u.id = m.user_id
                WHERE p.id = @product_id AND p.vendor_id = @vendor_id AND p.status = 'draft'
                  AND u.id = @user_id AND u.status = 'active'
                  AND m.status = 'active' AND m.role IN ('owner', 'manager', 'staff')
                  AND v.status = 'active'
            )
            """;
        await using (var preflight = writer.DataSource.CreateCommand(preflightSql))
        {
            preflight.Parameters.AddWithValue("user_id", userId);
            preflight.Parameters.AddWithValue("vendor_id", vendorId);
            preflight.Parameters.AddWithValue("product_id", productId);
            if (await preflight.ExecuteScalarAsync(cancellationToken) is not true)
                return null;
        }

        var extension = mimeType == "image/png" ? "png" : "jpg";
        var key = $"vendors/{vendorId:D}/products/{productId:D}/{Guid.NewGuid():N}.{extension}";
        var checksum = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        await store.PutAsync(key, bytes, mimeType, cancellationToken);
        try
        {
            const string sql = """
                INSERT INTO catalog.product_images (
                    product_id, storage_key, mime_type, width, height, sha256, status, is_primary
                )
                SELECT p.id, @storage_key, @mime_type, @width, @height, @sha256, 'active',
                       NOT EXISTS (
                           SELECT 1 FROM catalog.product_images existing
                           WHERE existing.product_id = p.id AND existing.is_primary
                             AND existing.variant_id IS NULL AND existing.archived_at IS NULL
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
                """;
            await using var command = writer.DataSource.CreateCommand(sql);
            command.Parameters.AddWithValue("user_id", userId);
            command.Parameters.AddWithValue("vendor_id", vendorId);
            command.Parameters.AddWithValue("product_id", productId);
            command.Parameters.AddWithValue("storage_key", key);
            command.Parameters.AddWithValue("mime_type", mimeType);
            command.Parameters.AddWithValue("width", width);
            command.Parameters.AddWithValue("height", height);
            command.Parameters.AddWithValue("sha256", checksum);
            var result = await command.ExecuteScalarAsync(cancellationToken);
            if (result is Guid imageId)
                return new UploadedProductImage(imageId, mimeType, width, height);
        }
        catch
        {
            await TryDeleteAsync(key);
            throw;
        }
        await TryDeleteAsync(key);
        return null;
    }

    private async Task TryDeleteAsync(string key)
    {
        try { await store.DeleteAsync(key, CancellationToken.None); }
        catch (Exception error) { logger.LogError(error, "Could not remove orphaned product image {StorageKey}", key); }
    }
}

public sealed class PostgresProductImageReader(NpgsqlDataSource reader, IProductImageObjectStore store)
    : IProductImageReader
{
    public async Task<ProductImageContent?> GetAsync(Guid userId, Guid vendorId, Guid productId,
        Guid imageId, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT im.storage_key, im.mime_type
            FROM catalog.product_images im
            JOIN catalog.products p ON p.id = im.product_id
            WHERE im.id = @image_id AND im.product_id = @product_id
              AND im.status = 'active' AND im.archived_at IS NULL
              AND p.vendor_id = @vendor_id AND p.status <> 'archived'
              AND EXISTS (
                  SELECT 1 FROM iam.vendor_memberships m
                  JOIN iam.users u ON u.id = m.user_id
                  JOIN catalog.vendors v ON v.id = m.vendor_id
                  WHERE m.user_id = @user_id AND m.vendor_id = @vendor_id
                    AND m.status = 'active' AND u.status = 'active' AND v.status = 'active'
              )
            """;
        await using var command = reader.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
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
        try { return new ProductImageContent(await store.GetAsync(key, cancellationToken), mimeType); }
        catch (AmazonS3Exception error) when (error.StatusCode == System.Net.HttpStatusCode.NotFound)
        {
            return null;
        }
        catch (FileNotFoundException)
        {
            return null;
        }
    }
}

public sealed class UnavailableProductImageStore : IProductImageWriter, IProductImageReader
{
    public Task<UploadedProductImage?> UploadAsync(Guid userId, Guid vendorId, Guid productId,
        byte[] bytes, string mimeType, int width, int height, CancellationToken cancellationToken) =>
        throw new ProductImageStoreUnavailableException();

    public Task<ProductImageContent?> GetAsync(Guid userId, Guid vendorId, Guid productId,
        Guid imageId, CancellationToken cancellationToken) =>
        throw new ProductImageStoreUnavailableException();
}
