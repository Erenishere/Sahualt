using Isopoh.Cryptography.Argon2;
using Npgsql;
using SahulatAI.Application.Features.Auth;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresVendorRegistrationWriter(RegistrationDataSource dataSource)
    : IVendorRegistrationWriter
{
    public async Task RegisterAsync(VendorRegistration registration, CancellationToken cancellationToken)
    {
        var passwordHash = Argon2.Hash(registration.Password);
        await using var connection = await dataSource.DataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        const string userSql = """
            INSERT INTO iam.users (email, email_normalized, password_hash, display_name, status)
            VALUES (@email, @normalized_email, @password_hash, @contact_name, 'pending')
            ON CONFLICT (email_normalized) DO NOTHING
            RETURNING id
            """;
        await using var userCommand = new NpgsqlCommand(userSql, connection, transaction);
        userCommand.Parameters.AddWithValue("email", registration.Email);
        userCommand.Parameters.AddWithValue("normalized_email", registration.Email.ToLowerInvariant());
        userCommand.Parameters.AddWithValue("password_hash", passwordHash);
        userCommand.Parameters.AddWithValue("contact_name", registration.ContactName);
        var userId = await userCommand.ExecuteScalarAsync(cancellationToken);
        if (userId is not Guid newUserId)
        {
            await transaction.RollbackAsync(cancellationToken);
            return;
        }

        const string vendorSql = """
            INSERT INTO catalog.vendors (display_name, slug, status, created_by_user_id)
            VALUES (@vendor_name, @slug, 'pending', @user_id)
            RETURNING id
            """;
        await using var vendorCommand = new NpgsqlCommand(vendorSql, connection, transaction);
        vendorCommand.Parameters.AddWithValue("vendor_name", registration.VendorName);
        vendorCommand.Parameters.AddWithValue("slug", "vendor-" + Guid.NewGuid().ToString("N"));
        vendorCommand.Parameters.AddWithValue("user_id", newUserId);
        var vendorId = (Guid)(await vendorCommand.ExecuteScalarAsync(cancellationToken)
            ?? throw new InvalidOperationException("Could not create pending vendor."));

        const string membershipSql = """
            INSERT INTO iam.vendor_memberships (vendor_id, user_id, role, status)
            VALUES (@vendor_id, @user_id, 'owner', 'pending')
            """;
        await using var membershipCommand = new NpgsqlCommand(membershipSql, connection, transaction);
        membershipCommand.Parameters.AddWithValue("vendor_id", vendorId);
        membershipCommand.Parameters.AddWithValue("user_id", newUserId);
        await membershipCommand.ExecuteNonQueryAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }
}

public sealed class PostgresCustomerRegistrationWriter(RegistrationDataSource dataSource)
    : ICustomerRegistrationWriter
{
    public async Task RegisterAsync(CustomerRegistration registration, CancellationToken cancellationToken)
    {
        var passwordHash = Argon2.Hash(registration.Password);
        await using var connection = await dataSource.DataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        const string userSql = """
            INSERT INTO iam.users (
                email, email_normalized, password_hash, display_name, status, email_verified_at
            )
            VALUES (@email, @normalized_email, @password_hash, @display_name, 'active', now())
            ON CONFLICT (email_normalized) DO NOTHING
            RETURNING id
            """;
        await using var userCommand = new NpgsqlCommand(userSql, connection, transaction);
        userCommand.Parameters.AddWithValue("email", registration.Email);
        userCommand.Parameters.AddWithValue("normalized_email", registration.Email.ToLowerInvariant());
        userCommand.Parameters.AddWithValue("password_hash", passwordHash);
        userCommand.Parameters.AddWithValue("display_name", registration.DisplayName);
        var userId = await userCommand.ExecuteScalarAsync(cancellationToken);
        if (userId is not Guid newUserId)
        {
            await transaction.RollbackAsync(cancellationToken);
            return;
        }

        const string profileSql = """
            INSERT INTO iam.user_roles (user_id, role) VALUES (@user_id, 'customer');
            INSERT INTO iam.customer_profiles (user_id, phone) VALUES (@user_id, @phone);
            """;
        await using var profileCommand = new NpgsqlCommand(profileSql, connection, transaction);
        profileCommand.Parameters.AddWithValue("user_id", newUserId);
        profileCommand.Parameters.AddWithValue("phone", (object?)registration.Phone ?? DBNull.Value);
        await profileCommand.ExecuteNonQueryAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }
}

public sealed class RegistrationDataSource(NpgsqlDataSource dataSource) : IAsyncDisposable
{
    public NpgsqlDataSource DataSource { get; } = dataSource;

    public ValueTask DisposeAsync() => DataSource.DisposeAsync();
}

public sealed class UnavailableVendorRegistrationWriter : IVendorRegistrationWriter
{
    public Task RegisterAsync(VendorRegistration registration, CancellationToken cancellationToken) =>
        throw new VendorRegistrationUnavailableException();
}

public sealed class UnavailableCustomerRegistrationWriter : ICustomerRegistrationWriter
{
    public Task RegisterAsync(CustomerRegistration registration, CancellationToken cancellationToken) =>
        throw new CustomerRegistrationUnavailableException();
}
