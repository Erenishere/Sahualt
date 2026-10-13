using System.Security.Cryptography;
using System.Diagnostics;
using System.Security.Principal;
using System.Text.Json;
using Isopoh.Cryptography.Argon2;
using Npgsql;

const string databaseName = "sahulat_ai_dev";
const string vendorEmail = "vendor@sahulat-ai.local";
const string vendorName = "Sahulat AI Test Vendor";
const string vendorSlug = "sahulat-ai-test-vendor";
const string adminEmail = "admin@sahulat-ai.local";

if (args.Length != 1 || args[0] != "--apply")
{
    Console.WriteLine("Plan only: create six least-privilege local API logins plus private test vendor and admin accounts in sahulat_ai_dev. Use --apply to write.");
    return;
}

var adminUrl = Environment.GetEnvironmentVariable("SAHULAT_ADMIN_DATABASE_URL");
if (!Uri.TryCreate(adminUrl, UriKind.Absolute, out var uri) ||
    uri.Scheme is not ("postgres" or "postgresql") ||
    uri.Host is not ("localhost" or "127.0.0.1" or "::1") ||
    uri.AbsolutePath.TrimStart('/') != databaseName)
    throw new InvalidOperationException("A private PostgreSQL URL for local sahulat_ai_dev is required.");

var credentials = uri.UserInfo.Split(':', 2);
if (credentials.Length != 2) throw new InvalidOperationException("The admin URL lacks credentials.");
var adminConnection = new NpgsqlConnectionStringBuilder
{
    Host = uri.Host,
    Port = uri.Port,
    Database = databaseName,
    Username = Uri.UnescapeDataString(credentials[0]),
    Password = Uri.UnescapeDataString(credentials[1]),
    Pooling = false,
    Timeout = 5,
    CommandTimeout = 5
};

var workspace = Directory.GetCurrentDirectory();
if (!File.Exists(Path.Combine(workspace, ".env.example")))
    throw new InvalidOperationException("Run from the Sahulat AI repository root.");
var secretPath = Path.Combine(workspace, "backend", ".local-runtime-secrets.json");
var roles = new[]
{
    (Login: "sahulat_api_assistant", Capability: "sahulat_assistant_reader", Password: NewPassword()),
    (Login: "sahulat_api_identity", Capability: "sahulat_identity_reader", Password: NewPassword()),
    (Login: "sahulat_api_catalog_writer", Capability: "sahulat_catalog_writer", Password: NewPassword()),
    (Login: "sahulat_api_registration", Capability: "sahulat_registration_writer", Password: NewPassword()),
    (Login: "sahulat_api_commerce", Capability: "sahulat_commerce_runtime", Password: NewPassword()),
    (Login: "sahulat_api_admin", Capability: "sahulat_admin_runtime", Password: NewPassword())
};
var vendorPassword = NewPassword();
var adminPassword = NewPassword();

await using var connection = new NpgsqlConnection(adminConnection.ConnectionString);
await connection.OpenAsync();
await using var transaction = await connection.BeginTransactionAsync();
var committed = false;
try
{
    await using (var preflight = new NpgsqlCommand("""
        SELECT current_setting('server_version_num')::int / 10000 = 18
           AND to_regclass('catalog.products') IS NOT NULL
           AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_assistant_reader')
           AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_identity_reader')
           AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_catalog_writer')
           AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_registration_writer')
           AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_commerce_runtime')
           AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahulat_admin_runtime')
           AND to_regclass('commerce.orders') IS NOT NULL
        """, connection, transaction))
    {
        if (await preflight.ExecuteScalarAsync() is not true)
            throw new InvalidOperationException("Catalog schema and capability roles must exist first.");
    }

    foreach (var role in roles)
    {
        await using var check = new NpgsqlCommand("""
            SELECT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole
                   AND NOT rolreplication AND NOT rolbypassrls
            FROM pg_roles WHERE rolname = @name
            """, connection, transaction);
        check.Parameters.AddWithValue("name", role.Login);
        var safe = await check.ExecuteScalarAsync();
        if (safe is false)
            throw new InvalidOperationException("An existing API role has unsafe attributes.");
        if (safe is null)
            await ExecuteAsync($"CREATE ROLE {role.Login} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS", connection, transaction);
        await ExecuteAsync($"ALTER ROLE {role.Login} PASSWORD '{role.Password}'", connection, transaction);
        await ExecuteAsync($"GRANT {role.Capability} TO {role.Login}", connection, transaction);
    }

    var passwordHash = Argon2.Hash(vendorPassword);
    await using var createUser = new NpgsqlCommand("""
        INSERT INTO iam.users (email, email_normalized, password_hash, display_name, status, email_verified_at)
        VALUES (@email, @email, @hash, @name, 'active', now())
        ON CONFLICT (email_normalized) DO UPDATE
        SET password_hash = EXCLUDED.password_hash, display_name = EXCLUDED.display_name,
            status = 'active', email_verified_at = now(), updated_at = now()
        RETURNING id
        """, connection, transaction);
    createUser.Parameters.AddWithValue("email", vendorEmail);
    createUser.Parameters.AddWithValue("hash", passwordHash);
    createUser.Parameters.AddWithValue("name", vendorName);
    var userId = (Guid)(await createUser.ExecuteScalarAsync()
        ?? throw new InvalidOperationException("Could not create local vendor user."));

    await using var createVendor = new NpgsqlCommand("""
        INSERT INTO catalog.vendors (display_name, slug, status, created_by_user_id)
        VALUES (@name, @slug, 'active', @user_id)
        ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name, status = 'active', updated_at = now()
        RETURNING id
        """, connection, transaction);
    createVendor.Parameters.AddWithValue("name", vendorName);
    createVendor.Parameters.AddWithValue("slug", vendorSlug);
    createVendor.Parameters.AddWithValue("user_id", userId);
    var vendorId = (Guid)(await createVendor.ExecuteScalarAsync()
        ?? throw new InvalidOperationException("Could not create local vendor."));

    await using var membership = new NpgsqlCommand("""
        INSERT INTO iam.vendor_memberships (vendor_id, user_id, role, status)
        VALUES (@vendor_id, @user_id, 'owner', 'active')
        ON CONFLICT (vendor_id, user_id) DO UPDATE
        SET role = 'owner', status = 'active', updated_at = now()
        """, connection, transaction);
    membership.Parameters.AddWithValue("vendor_id", vendorId);
    membership.Parameters.AddWithValue("user_id", userId);
    await membership.ExecuteNonQueryAsync();

    var adminHash = Argon2.Hash(adminPassword);
    await using var createAdmin = new NpgsqlCommand("""
        INSERT INTO iam.users (email, email_normalized, password_hash, display_name, status, email_verified_at)
        VALUES (@email, @email, @hash, 'Sahulat AI Local Admin', 'active', now())
        ON CONFLICT (email_normalized) DO UPDATE
        SET password_hash = EXCLUDED.password_hash, status = 'active', email_verified_at = now(), updated_at = now()
        RETURNING id
        """, connection, transaction);
    createAdmin.Parameters.AddWithValue("email", adminEmail);
    createAdmin.Parameters.AddWithValue("hash", adminHash);
    var adminUserId = (Guid)(await createAdmin.ExecuteScalarAsync()
        ?? throw new InvalidOperationException("Could not create local admin user."));
    await using var createAdminRole = new NpgsqlCommand("""
        INSERT INTO iam.user_roles (user_id, role, status) VALUES (@user_id, 'platform_admin', 'active')
        ON CONFLICT (user_id, role) DO UPDATE SET status = 'active', updated_at = now()
        """, connection, transaction);
    createAdminRole.Parameters.AddWithValue("user_id", adminUserId);
    await createAdminRole.ExecuteNonQueryAsync();

    await transaction.CommitAsync();
    committed = true;

    var secrets = new
    {
        databaseName,
        host = uri.Host,
        port = uri.Port,
        assistant = roles[0].Password,
        identity = roles[1].Password,
        catalogWriter = roles[2].Password,
        registration = roles[3].Password,
        commerce = roles[4].Password,
        admin = roles[5].Password,
        vendorEmail,
        vendorPassword,
        adminEmail,
        adminPassword
    };
    await File.WriteAllTextAsync(secretPath, JsonSerializer.Serialize(secrets));
    if (OperatingSystem.IsWindows())
    {
        var sid = WindowsIdentity.GetCurrent().User?.Value
            ?? throw new InvalidOperationException("Could not identify the local user for secret file access.");
        using var acl = Process.Start(new ProcessStartInfo("icacls.exe")
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            ArgumentList = { secretPath, "/inheritance:r", "/grant:r", $"*{sid}:F" }
        }) ?? throw new InvalidOperationException("Could not secure the local secrets file.");
        await acl.WaitForExitAsync();
        if (acl.ExitCode != 0)
        {
            File.Delete(secretPath);
            throw new InvalidOperationException("Could not secure the local secrets file; it was removed.");
        }
    }
    Console.WriteLine("Local API roles, test vendor, and test admin are ready. Credentials are in the ignored backend/.local-runtime-secrets.json file; no password was printed.");
}
catch
{
    if (!committed) await transaction.RollbackAsync();
    throw;
}

static string NewPassword() => Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();

static async Task ExecuteAsync(string sql, NpgsqlConnection connection, NpgsqlTransaction transaction)
{
    await using var command = new NpgsqlCommand(sql, connection, transaction);
    await command.ExecuteNonQueryAsync();
}
