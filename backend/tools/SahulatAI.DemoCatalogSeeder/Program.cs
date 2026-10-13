using System.Diagnostics;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using Isopoh.Cryptography.Argon2;
using Npgsql;
using SkiaSharp;

const string DatasetId = "SAHULAT-3-DEMO-STORES-V1";
const string DatabaseName = "sahulat_ai_dev";
const string ArchiveCatalogPath = "sahulat_3_demo_stores/data/catalog.json";
const string AssetPrefix = "sahulat_3_demo_stores/public/demo/stores/";

var archivePath = ReadOption(args, "--archive");
var apply = args.Contains("--apply", StringComparer.Ordinal);
var purge = args.Contains("--purge", StringComparer.Ordinal);
var clientFacing = args.Contains("--client-facing", StringComparer.Ordinal);
if (string.IsNullOrWhiteSpace(archivePath) || !File.Exists(archivePath))
    throw new InvalidOperationException("A valid --archive path is required.");
if (apply && purge) throw new InvalidOperationException("Choose either --apply or --purge.");
if (clientFacing && (!apply || purge))
    throw new InvalidOperationException("--client-facing requires --apply and cannot be combined with --purge.");

var workspace = Directory.GetCurrentDirectory();
if (!File.Exists(Path.Combine(workspace, ".env.example")))
    throw new InvalidOperationException("Run from the Sahulat AI repository root.");

using var archive = ZipFile.OpenRead(Path.GetFullPath(archivePath));
var catalog = ReadCatalog(archive);
ValidateCatalog(catalog, archive);

if (!apply && !purge)
{
    Console.WriteLine($"Plan only: import {catalog.Stores.Count} isolated demo vendors and {catalog.Products.Count} draft products from {DatasetId}. Use -Apply to write.");
    return;
}

if (Environment.GetEnvironmentVariable("SAHULAT_ENABLE_DEMO_CATALOG") != "1")
    throw new InvalidOperationException("The local demo catalog safety gate is not enabled.");

var connectionString = BuildLocalConnectionString(
    Environment.GetEnvironmentVariable("SAHULAT_ADMIN_DATABASE_URL"));
var expectedMediaRoot = Path.GetFullPath(Path.Combine(workspace, "backend", ".local-media"));
var mediaRoot = Path.GetFullPath(Environment.GetEnvironmentVariable("SAHULAT_DEMO_MEDIA_ROOT") ?? "");
if (!string.Equals(mediaRoot, expectedMediaRoot, StringComparison.OrdinalIgnoreCase))
    throw new InvalidOperationException("Demo media must use backend/.local-media.");

var frontendDemoRoot = Path.GetFullPath(Path.Combine(workspace, "frontend", "public", "demo", "stores"));
var secretsPath = Path.GetFullPath(Path.Combine(workspace, "backend", ".local-demo-vendor-secrets.json"));

await using var connection = new NpgsqlConnection(connectionString.ConnectionString);
await connection.OpenAsync();
await EnsureLocalSchemaAsync(connection);

if (purge)
{
    await PurgeAsync(connection, catalog, mediaRoot, frontendDemoRoot, secretsPath);
    Console.WriteLine($"Purged {DatasetId} vendors, products, media, and local credentials.");
    return;
}

ExtractFrontendAssets(archive, frontendDemoRoot);
var credentials = LoadOrCreateCredentials(secretsPath, catalog.Stores);
await SeedAsync(connection, archive, catalog, credentials, mediaRoot, clientFacing);
await WriteSecretsAsync(secretsPath, credentials);
var visibility = clientFacing ? "client-facing demo products (unavailable until real stock is configured)" : "draft products";
Console.WriteLine($"Created or refreshed {catalog.Stores.Count} local demo vendors and {catalog.Products.Count} {visibility}. Credentials are stored in the ignored backend/.local-demo-vendor-secrets.json file; no password was printed.");

static async Task SeedAsync(NpgsqlConnection connection, ZipArchive archive, DemoCatalog catalog,
    IReadOnlyDictionary<string, DemoCredential> credentials, string mediaRoot, bool clientFacing)
{
    var productStatus = clientFacing ? "published" : "draft";
    var variantStatus = clientFacing ? "active" : "draft";
    var listingStatus = clientFacing ? "active" : "draft";
    var availability = clientFacing ? "unavailable" : "unknown";
    var publishedAtSql = clientFacing ? "now()" : "NULL";
    await using var transaction = await connection.BeginTransactionAsync();
    try
    {
        var categoryIds = new Dictionary<string, Guid>(StringComparer.Ordinal);
        foreach (var store in catalog.Stores)
        {
            var storeId = Guid.Parse(store.Id);
            var userId = DeriveGuid(storeId, "owner");
            var credential = credentials[store.Slug];
            await EnsureIdentityIsAvailableAsync(connection, transaction, userId, credential.Email, storeId, store.Slug);

            await ExecuteAsync(connection, transaction, """
                INSERT INTO iam.users (
                    id, email, email_normalized, password_hash, display_name,
                    status, email_verified_at, archived_at
                ) VALUES (
                    @id, @email, @email, @password_hash, @display_name,
                    'active', now(), NULL
                )
                ON CONFLICT (id) DO UPDATE SET
                    email = EXCLUDED.email,
                    email_normalized = EXCLUDED.email_normalized,
                    password_hash = EXCLUDED.password_hash,
                    display_name = EXCLUDED.display_name,
                    status = 'active',
                    email_verified_at = COALESCE(iam.users.email_verified_at, now()),
                    archived_at = NULL,
                    updated_at = now()
                """, new()
            {
                ["id"] = userId,
                ["email"] = credential.Email,
                ["password_hash"] = Argon2.Hash(credential.Password),
                ["display_name"] = $"{store.Name} Demo Owner"
            });

            await ExecuteAsync(connection, transaction, """
                INSERT INTO catalog.vendors (
                    id, display_name, slug, status, created_by_user_id,
                    description, allow_customer_offers, archived_at
                ) VALUES (
                    @id, @display_name, @slug, 'active', @user_id,
                    @description, false, NULL
                )
                ON CONFLICT (id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    slug = EXCLUDED.slug,
                    status = 'active',
                    created_by_user_id = EXCLUDED.created_by_user_id,
                    description = EXCLUDED.description,
                    allow_customer_offers = false,
                    archived_at = NULL,
                    updated_at = now()
                """, new()
            {
                ["id"] = storeId,
                ["display_name"] = store.Name,
                ["slug"] = store.Slug,
                ["user_id"] = userId,
                ["description"] = $"DEMO CATALOG: {store.Description} Fictional local-development content; not a verified merchant."
            });

            await ExecuteAsync(connection, transaction, """
                INSERT INTO iam.vendor_memberships (vendor_id, user_id, role, status)
                VALUES (@vendor_id, @user_id, 'owner', 'active')
                ON CONFLICT (vendor_id, user_id) DO UPDATE SET
                    role = 'owner', status = 'active', updated_at = now()
                """, new() { ["vendor_id"] = storeId, ["user_id"] = userId });
        }

        foreach (var category in catalog.Categories)
        {
            var archiveCategoryId = Guid.Parse(category.Id);
            var existingId = await ScalarGuidAsync(connection, transaction,
                "SELECT id FROM catalog.categories WHERE slug = @slug", new() { ["slug"] = category.Slug });
            var categoryId = existingId ?? archiveCategoryId;
            if (existingId is null)
            {
                await ExecuteAsync(connection, transaction, """
                    INSERT INTO catalog.categories (id, name, slug, status, sort_order, archived_at)
                    VALUES (@id, @name, @slug, 'active', @sort_order, NULL)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name, slug = EXCLUDED.slug, status = 'active',
                        sort_order = EXCLUDED.sort_order, archived_at = NULL, updated_at = now()
                    """, new()
                {
                    ["id"] = categoryId,
                    ["name"] = category.Name,
                    ["slug"] = category.Slug,
                    ["sort_order"] = categoryIds.Count
                });
            }
            categoryIds[$"{category.StoreSlug}/{category.Slug}"] = categoryId;
        }

        foreach (var product in catalog.Products)
        {
            var productId = Guid.Parse(product.Id);
            var vendorId = Guid.Parse(product.StoreId);
            var ownerId = DeriveGuid(vendorId, "owner");
            var variantId = DeriveGuid(productId, "variant");
            var listingId = DeriveGuid(productId, "listing");
            var imageId = DeriveGuid(productId, "image");
            var categoryId = categoryIds[$"{product.StoreSlug}/{product.CategorySlug}"];
            await EnsureProductIsAvailableAsync(connection, transaction, productId, vendorId);

            await ExecuteAsync(connection, transaction, $"""
                INSERT INTO catalog.products (
                    id, vendor_id, category_id, name, description, brand_name, status,
                    published_at, created_by_user_id, updated_by_user_id, archived_at
                ) VALUES (
                    @id, @vendor_id, @category_id, @name, @description, @brand_name, @product_status,
                    {publishedAtSql}, @owner_id, @owner_id, NULL
                )
                ON CONFLICT (id) DO UPDATE SET
                    category_id = EXCLUDED.category_id,
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    brand_name = EXCLUDED.brand_name,
                    status = EXCLUDED.status,
                    published_at = EXCLUDED.published_at,
                    updated_by_user_id = EXCLUDED.updated_by_user_id,
                    archived_at = NULL,
                    updated_at = now()
                """, new()
            {
                ["id"] = productId,
                ["vendor_id"] = vendorId,
                ["category_id"] = categoryId,
                ["name"] = product.Name,
                ["description"] = $"{product.Description} DEMO: illustrative local-development product.",
                ["brand_name"] = (object?)product.Brand ?? DBNull.Value,
                ["owner_id"] = ownerId,
                ["product_status"] = productStatus
            });

            await ExecuteAsync(connection, transaction, """
                INSERT INTO catalog.product_variants (
                    id, product_id, variant_code, sku, status, is_default, archived_at
                ) VALUES (@id, @product_id, 'default', @sku, @variant_status, true, NULL)
                ON CONFLICT (id) DO UPDATE SET
                    variant_code = 'default', sku = EXCLUDED.sku, status = EXCLUDED.status,
                    is_default = true, archived_at = NULL, updated_at = now()
                """, new()
            {
                ["id"] = variantId,
                ["product_id"] = productId,
                ["sku"] = product.Sku,
                ["variant_status"] = variantStatus
            });

            await ExecuteAsync(connection, transaction, """
                INSERT INTO catalog.listings (
                    id, variant_id, price, currency, availability, status,
                    allow_customer_offers, archived_at
                ) VALUES (
                    @id, @variant_id, @price, @currency, @availability, @listing_status, false, NULL
                )
                ON CONFLICT (id) DO UPDATE SET
                    price = EXCLUDED.price, currency = EXCLUDED.currency,
                    availability = EXCLUDED.availability, status = EXCLUDED.status,
                    allow_customer_offers = false, archived_at = NULL, updated_at = now()
                """, new()
            {
                ["id"] = listingId,
                ["variant_id"] = variantId,
                ["price"] = product.PriceAmount,
                ["currency"] = product.Currency,
                ["availability"] = availability,
                ["listing_status"] = listingStatus
            });

            var normalizedImage = NormalizeProductImage(archive, product.PrimaryImageFile);
            var storageKey = $"vendors/{vendorId:D}/products/{productId:D}/{imageId:N}.jpg";
            var destination = ResolveMediaPath(mediaRoot, storageKey);
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
            await File.WriteAllBytesAsync(destination, normalizedImage.Bytes);
            var checksum = Convert.ToHexString(SHA256.HashData(normalizedImage.Bytes)).ToLowerInvariant();

            await ExecuteAsync(connection, transaction, """
                INSERT INTO catalog.product_images (
                    id, product_id, storage_key, source_url, mime_type, width, height,
                    sha256, sort_order, is_primary, status, archived_at
                ) VALUES (
                    @id, @product_id, @storage_key, @source_url, 'image/jpeg', @width, @height,
                    @sha256, 0, true, 'active', NULL
                )
                ON CONFLICT (id) DO UPDATE SET
                    storage_key = EXCLUDED.storage_key,
                    source_url = EXCLUDED.source_url,
                    mime_type = 'image/jpeg', width = EXCLUDED.width, height = EXCLUDED.height,
                    sha256 = EXCLUDED.sha256, sort_order = 0, is_primary = true,
                    status = 'active', archived_at = NULL, updated_at = now()
                """, new()
            {
                ["id"] = imageId,
                ["product_id"] = productId,
                ["storage_key"] = storageKey,
                ["source_url"] = product.PrimaryImageUrl,
                ["width"] = normalizedImage.Width,
                ["height"] = normalizedImage.Height,
                ["sha256"] = checksum
            });
        }

        await transaction.CommitAsync();
    }
    catch
    {
        await transaction.RollbackAsync();
        throw;
    }
}

static async Task PurgeAsync(NpgsqlConnection connection, DemoCatalog catalog, string mediaRoot,
    string frontendDemoRoot, string secretsPath)
{
    var productIds = catalog.Products.Select(product => Guid.Parse(product.Id)).ToArray();
    var vendorIds = catalog.Stores.Select(store => Guid.Parse(store.Id)).ToArray();
    var userIds = vendorIds.Select(vendorId => DeriveGuid(vendorId, "owner")).ToArray();
    var categoryIds = catalog.Categories.Select(category => Guid.Parse(category.Id)).ToArray();
    await using var transaction = await connection.BeginTransactionAsync();
    try
    {
        await ExecuteAsync(connection, transaction,
            "DELETE FROM catalog.product_images WHERE product_id = ANY(@ids)", new() { ["ids"] = productIds });
        await ExecuteAsync(connection, transaction, """
            DELETE FROM catalog.listings WHERE variant_id IN (
                SELECT id FROM catalog.product_variants WHERE product_id = ANY(@ids)
            )
            """, new() { ["ids"] = productIds });
        await ExecuteAsync(connection, transaction,
            "DELETE FROM catalog.product_variants WHERE product_id = ANY(@ids)", new() { ["ids"] = productIds });
        await ExecuteAsync(connection, transaction,
            "DELETE FROM catalog.products WHERE id = ANY(@ids)", new() { ["ids"] = productIds });
        await ExecuteAsync(connection, transaction,
            "DELETE FROM iam.vendor_memberships WHERE vendor_id = ANY(@ids) AND user_id = ANY(@user_ids)",
            new() { ["ids"] = vendorIds, ["user_ids"] = userIds });
        await ExecuteAsync(connection, transaction,
            "DELETE FROM catalog.vendors WHERE id = ANY(@ids)", new() { ["ids"] = vendorIds });
        await ExecuteAsync(connection, transaction,
            "DELETE FROM iam.users WHERE id = ANY(@ids)", new() { ["ids"] = userIds });
        await ExecuteAsync(connection, transaction, """
            DELETE FROM catalog.categories c
            WHERE c.id = ANY(@ids)
              AND NOT EXISTS (SELECT 1 FROM catalog.products p WHERE p.category_id = c.id)
              AND NOT EXISTS (SELECT 1 FROM catalog.categories child WHERE child.parent_id = c.id)
            """, new() { ["ids"] = categoryIds });
        await transaction.CommitAsync();
    }
    catch
    {
        await transaction.RollbackAsync();
        throw;
    }

    foreach (var store in catalog.Stores)
    {
        DeleteContainedDirectory(mediaRoot, Path.Combine(mediaRoot, "vendors", Guid.Parse(store.Id).ToString("D")));
        DeleteContainedDirectory(frontendDemoRoot, Path.Combine(frontendDemoRoot, store.Slug));
    }
    if (File.Exists(secretsPath)) File.Delete(secretsPath);
}

static DemoCatalog ReadCatalog(ZipArchive archive)
{
    var entry = archive.GetEntry(ArchiveCatalogPath)
        ?? throw new InvalidDataException($"Archive entry is missing: {ArchiveCatalogPath}");
    using var stream = entry.Open();
    return JsonSerializer.Deserialize<DemoCatalog>(stream, new JsonSerializerOptions
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
    }) ?? throw new InvalidDataException("The demo catalog JSON is invalid.");
}

static void ValidateCatalog(DemoCatalog catalog, ZipArchive archive)
{
    if (catalog.DatasetId != DatasetId || !catalog.NonproductionData || catalog.Stores.Count != 3 ||
        catalog.Categories.Count != 18 || catalog.Products.Count != 21)
        throw new InvalidDataException("The archive is not the expected nonproduction demo dataset.");
    if (catalog.Stores.Any(store => !store.IsDemo || store.StorefrontStatus != "draft" ||
            store.VerificationStatus != "unverified" || store.CountryCode != "PK" || store.Currency != "PKR"))
        throw new InvalidDataException("Every demo store must remain draft, unverified, and Pakistan/PKR scoped.");
    if (catalog.Products.Any(product => !product.IsDemo || product.ListingStatus != "draft" ||
            product.InventoryTracked || product.InventoryQuantity is not null || product.Rating is not null ||
            product.ReviewCount is not null || product.Currency != "PKR" || product.PriceAmount <= 0))
        throw new InvalidDataException("Demo products must remain unrated drafts with unknown inventory.");
    EnsureUnique(catalog.Stores.Select(store => store.Id), "store IDs");
    EnsureUnique(catalog.Stores.Select(store => store.Slug), "store slugs");
    EnsureUnique(catalog.Products.Select(product => product.Id), "product IDs");
    EnsureUnique(catalog.Products.Select(product => product.Sku), "product SKUs");
    var storeIds = catalog.Stores.Select(store => store.Id).ToHashSet(StringComparer.Ordinal);
    var categories = catalog.Categories.Select(category => $"{category.StoreSlug}/{category.Slug}")
        .ToHashSet(StringComparer.Ordinal);
    foreach (var product in catalog.Products)
    {
        _ = Guid.Parse(product.Id);
        if (!storeIds.Contains(product.StoreId) || !categories.Contains($"{product.StoreSlug}/{product.CategorySlug}"))
            throw new InvalidDataException($"Product {product.Id} has an invalid store or category reference.");
        var entryName = "sahulat_3_demo_stores/" + product.PrimaryImageFile.Replace('\\', '/');
        if (archive.GetEntry(entryName) is not { Length: > 0 })
            throw new InvalidDataException($"Product image is missing: {entryName}");
    }
}

static void ExtractFrontendAssets(ZipArchive archive, string frontendDemoRoot)
{
    Directory.CreateDirectory(frontendDemoRoot);
    foreach (var entry in archive.Entries.Where(entry =>
                 entry.FullName.StartsWith(AssetPrefix, StringComparison.Ordinal) && entry.Length > 0))
    {
        var relative = entry.FullName[AssetPrefix.Length..].Replace('/', Path.DirectorySeparatorChar);
        var destination = Path.GetFullPath(Path.Combine(frontendDemoRoot, relative));
        EnsureContained(frontendDemoRoot, destination);
        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
        entry.ExtractToFile(destination, overwrite: true);
    }
}

static NormalizedImage NormalizeProductImage(ZipArchive archive, string imageFile)
{
    var entryName = "sahulat_3_demo_stores/" + imageFile.Replace('\\', '/');
    var entry = archive.GetEntry(entryName)
        ?? throw new InvalidDataException($"Product image is missing: {entryName}");
    using var stream = entry.Open();
    using var codec = SKCodec.Create(stream)
        ?? throw new InvalidDataException($"Product image cannot be decoded: {entryName}");
    if (codec.Info.Width is < 1 or > 6000 || codec.Info.Height is < 1 or > 6000 ||
        (long)codec.Info.Width * codec.Info.Height > 20_000_000)
        throw new InvalidDataException($"Product image dimensions are invalid: {entryName}");
    using var bitmap = SKBitmap.Decode(codec)
        ?? throw new InvalidDataException($"Product image cannot be decoded: {entryName}");
    using var image = SKImage.FromBitmap(bitmap);
    using var encoded = image.Encode(SKEncodedImageFormat.Jpeg, 88)
        ?? throw new InvalidDataException($"Product image cannot be encoded: {entryName}");
    return new NormalizedImage(encoded.ToArray(), codec.Info.Width, codec.Info.Height);
}

static Dictionary<string, DemoCredential> LoadOrCreateCredentials(string secretsPath,
    IReadOnlyList<DemoStore> stores)
{
    var credentials = new Dictionary<string, DemoCredential>(StringComparer.Ordinal);
    if (File.Exists(secretsPath))
    {
        using var document = JsonDocument.Parse(File.ReadAllText(secretsPath));
        if (document.RootElement.TryGetProperty("datasetId", out var dataset) &&
            dataset.GetString() == DatasetId &&
            document.RootElement.TryGetProperty("vendors", out var vendors))
        {
            foreach (var vendor in vendors.EnumerateArray())
            {
                var slug = vendor.GetProperty("slug").GetString();
                var email = vendor.GetProperty("email").GetString();
                var password = vendor.GetProperty("password").GetString();
                if (!string.IsNullOrWhiteSpace(slug) && !string.IsNullOrWhiteSpace(email) &&
                    !string.IsNullOrWhiteSpace(password))
                    credentials[slug] = new DemoCredential(email, password);
            }
        }
    }
    foreach (var store in stores)
    {
        if (!credentials.ContainsKey(store.Slug))
            credentials[store.Slug] = new DemoCredential(
                $"owner+{store.Slug}@demo.sahulat-ai.local",
                Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant());
    }
    return credentials;
}

static async Task WriteSecretsAsync(string secretsPath,
    IReadOnlyDictionary<string, DemoCredential> credentials)
{
    var payload = new
    {
        datasetId = DatasetId,
        vendors = credentials.OrderBy(pair => pair.Key).Select(pair => new
        {
            slug = pair.Key,
            email = pair.Value.Email,
            password = pair.Value.Password
        })
    };
    await File.WriteAllTextAsync(secretsPath,
        JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true }));
    if (!OperatingSystem.IsWindows()) return;
    var sid = WindowsIdentity.GetCurrent().User?.Value
        ?? throw new InvalidOperationException("Could not identify the local user for secret file access.");
    using var acl = Process.Start(new ProcessStartInfo("icacls.exe")
    {
        UseShellExecute = false,
        CreateNoWindow = true,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        ArgumentList = { secretsPath, "/inheritance:r", "/grant:r", $"*{sid}:F" }
    }) ?? throw new InvalidOperationException("Could not secure the local demo credential file.");
    await acl.WaitForExitAsync();
    if (acl.ExitCode != 0)
    {
        File.Delete(secretsPath);
        throw new InvalidOperationException("Could not secure the local demo credential file; it was removed.");
    }
}

static NpgsqlConnectionStringBuilder BuildLocalConnectionString(string? value)
{
    if (!Uri.TryCreate(value, UriKind.Absolute, out var uri) ||
        uri.Scheme is not ("postgres" or "postgresql") ||
        uri.Host is not ("localhost" or "127.0.0.1" or "::1") ||
        uri.AbsolutePath.TrimStart('/') != DatabaseName)
        throw new InvalidOperationException("A private PostgreSQL URL for local sahulat_ai_dev is required.");
    var credentials = uri.UserInfo.Split(':', 2);
    if (credentials.Length != 2) throw new InvalidOperationException("The local database URL lacks credentials.");
    return new NpgsqlConnectionStringBuilder
    {
        Host = uri.Host,
        Port = uri.Port,
        Database = DatabaseName,
        Username = Uri.UnescapeDataString(credentials[0]),
        Password = Uri.UnescapeDataString(credentials[1]),
        Pooling = false,
        Timeout = 5,
        CommandTimeout = 15
    };
}

static async Task EnsureLocalSchemaAsync(NpgsqlConnection connection)
{
    await using var command = new NpgsqlCommand("""
        SELECT current_database() = 'sahulat_ai_dev'
           AND current_setting('server_version_num')::int / 10000 = 18
           AND to_regclass('catalog.products') IS NOT NULL
           AND to_regclass('catalog.product_images') IS NOT NULL
           AND EXISTS (
               SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'catalog' AND table_name = 'vendors'
                 AND column_name = 'description'
           )
        """, connection);
    if (await command.ExecuteScalarAsync() is not true)
        throw new InvalidOperationException("PostgreSQL 18 with the current Sahulat catalog schema is required.");
}

static async Task EnsureIdentityIsAvailableAsync(NpgsqlConnection connection, NpgsqlTransaction transaction,
    Guid userId, string email, Guid vendorId, string slug)
{
    await using var command = new NpgsqlCommand("""
        SELECT EXISTS (SELECT 1 FROM iam.users WHERE id = @user_id AND email_normalized <> @email)
            OR EXISTS (SELECT 1 FROM iam.users WHERE email_normalized = @email AND id <> @user_id)
            OR EXISTS (SELECT 1 FROM catalog.vendors WHERE id = @vendor_id AND slug <> @slug)
            OR EXISTS (SELECT 1 FROM catalog.vendors WHERE slug = @slug AND id <> @vendor_id)
        """, connection, transaction);
    command.Parameters.AddWithValue("user_id", userId);
    command.Parameters.AddWithValue("email", email);
    command.Parameters.AddWithValue("vendor_id", vendorId);
    command.Parameters.AddWithValue("slug", slug);
    if (await command.ExecuteScalarAsync() is true)
        throw new InvalidOperationException($"A non-demo identity already uses the deterministic ID, email, or slug for {slug}.");
}

static async Task EnsureProductIsAvailableAsync(NpgsqlConnection connection, NpgsqlTransaction transaction,
    Guid productId, Guid vendorId)
{
    await using var command = new NpgsqlCommand("""
        SELECT EXISTS (
            SELECT 1 FROM catalog.products WHERE id = @product_id AND vendor_id <> @vendor_id
        )
        """, connection, transaction);
    command.Parameters.AddWithValue("product_id", productId);
    command.Parameters.AddWithValue("vendor_id", vendorId);
    if (await command.ExecuteScalarAsync() is true)
        throw new InvalidOperationException($"Product ID {productId:D} already belongs to another vendor.");
}

static async Task ExecuteAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, string sql,
    Dictionary<string, object> parameters)
{
    await using var command = new NpgsqlCommand(sql, connection, transaction);
    foreach (var parameter in parameters) command.Parameters.AddWithValue(parameter.Key, parameter.Value);
    await command.ExecuteNonQueryAsync();
}

static async Task<Guid?> ScalarGuidAsync(NpgsqlConnection connection, NpgsqlTransaction transaction,
    string sql, Dictionary<string, object> parameters)
{
    await using var command = new NpgsqlCommand(sql, connection, transaction);
    foreach (var parameter in parameters) command.Parameters.AddWithValue(parameter.Key, parameter.Value);
    var value = await command.ExecuteScalarAsync();
    return value is Guid id ? id : null;
}

static Guid DeriveGuid(Guid source, string purpose)
{
    var hash = SHA256.HashData(Encoding.UTF8.GetBytes($"{DatasetId}:{source:D}:{purpose}"));
    hash[6] = (byte)((hash[6] & 0x0F) | 0x50);
    hash[8] = (byte)((hash[8] & 0x3F) | 0x80);
    return new Guid(hash[..16], bigEndian: true);
}

static string ResolveMediaPath(string mediaRoot, string storageKey)
{
    var destination = Path.GetFullPath(Path.Combine(mediaRoot,
        storageKey.Replace('/', Path.DirectorySeparatorChar)));
    EnsureContained(mediaRoot, destination);
    return destination;
}

static void DeleteContainedDirectory(string root, string target)
{
    var fullTarget = Path.GetFullPath(target);
    EnsureContained(root, fullTarget);
    if (Directory.Exists(fullTarget)) Directory.Delete(fullTarget, recursive: true);
}

static void EnsureContained(string root, string path)
{
    var fullRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
    if (!path.StartsWith(fullRoot, StringComparison.OrdinalIgnoreCase))
        throw new InvalidOperationException($"Path escapes the expected root: {path}");
}

static void EnsureUnique(IEnumerable<string> values, string label)
{
    var all = values.ToArray();
    if (all.Distinct(StringComparer.Ordinal).Count() != all.Length)
        throw new InvalidDataException($"The demo catalog contains duplicate {label}.");
}

static string? ReadOption(string[] arguments, string option)
{
    var index = Array.IndexOf(arguments, option);
    return index >= 0 && index + 1 < arguments.Length ? arguments[index + 1] : null;
}

sealed record DemoCredential(string Email, string Password);
sealed record NormalizedImage(byte[] Bytes, int Width, int Height);

sealed class DemoCatalog
{
    public required string DatasetId { get; init; }
    public required bool NonproductionData { get; init; }
    public required List<DemoStore> Stores { get; init; }
    public required List<DemoCategory> Categories { get; init; }
    public required List<DemoProduct> Products { get; init; }
}

sealed class DemoStore
{
    public required string Id { get; init; }
    public required string Slug { get; init; }
    public required string Name { get; init; }
    public required string Description { get; init; }
    public required string VerificationStatus { get; init; }
    public required string StorefrontStatus { get; init; }
    public required bool IsDemo { get; init; }
    public required string CountryCode { get; init; }
    public required string Currency { get; init; }
}

sealed class DemoCategory
{
    public required string Id { get; init; }
    public required string StoreSlug { get; init; }
    public required string Name { get; init; }
    public required string Slug { get; init; }
}

sealed class DemoProduct
{
    public required string Id { get; init; }
    public required string StoreId { get; init; }
    public required string StoreSlug { get; init; }
    public required string Sku { get; init; }
    public required string Name { get; init; }
    public required string CategorySlug { get; init; }
    public required string Description { get; init; }
    public required decimal PriceAmount { get; init; }
    public required string Currency { get; init; }
    public required string PrimaryImageUrl { get; init; }
    public required string PrimaryImageFile { get; init; }
    public required bool IsDemo { get; init; }
    public required string ListingStatus { get; init; }
    public int? InventoryQuantity { get; init; }
    public required bool InventoryTracked { get; init; }
    public decimal? Rating { get; init; }
    public int? ReviewCount { get; init; }
    public string? Brand { get; init; }
}
