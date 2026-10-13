using Npgsql;
using NpgsqlTypes;
using SahulatAI.Application.Features.Marketplace;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class CommerceDataSource(NpgsqlDataSource dataSource) : IAsyncDisposable
{
    public NpgsqlDataSource DataSource { get; } = dataSource;
    public ValueTask DisposeAsync() => DataSource.DisposeAsync();
}

public sealed class PostgresAccountStore(CommerceDataSource commerce) : IAccountStore
{
    public async Task<AccountProfile?> GetProfileAsync(Guid userId, CancellationToken cancellationToken)
    {
        const string profileSql = """
            SELECT u.id, u.email, u.display_name, cp.phone
            FROM iam.users u
            JOIN iam.user_roles r ON r.user_id = u.id AND r.role = 'customer' AND r.status = 'active'
            JOIN iam.customer_profiles cp ON cp.user_id = u.id
            WHERE u.id = @user_id AND u.status = 'active'
            """;
        await using var profileCommand = commerce.DataSource.CreateCommand(profileSql);
        profileCommand.Parameters.AddWithValue("user_id", userId);
        string email;
        string displayName;
        string? phone;
        await using (var reader = await profileCommand.ExecuteReaderAsync(cancellationToken))
        {
            if (!await reader.ReadAsync(cancellationToken)) return null;
            email = reader.GetString(1);
            displayName = reader.GetString(2);
            phone = reader.IsDBNull(3) ? null : reader.GetString(3);
        }

        const string addressesSql = """
            SELECT id, label, recipient_name, phone, address_line1, address_line2,
                   city, province, postal_code, is_default
            FROM iam.customer_addresses
            WHERE user_id = @user_id AND archived_at IS NULL
            ORDER BY is_default DESC, created_at, id
            LIMIT 50
            """;
        await using var addressesCommand = commerce.DataSource.CreateCommand(addressesSql);
        addressesCommand.Parameters.AddWithValue("user_id", userId);
        await using var addressesReader = await addressesCommand.ExecuteReaderAsync(cancellationToken);
        var addresses = new List<CustomerAddress>();
        while (await addressesReader.ReadAsync(cancellationToken))
            addresses.Add(ReadAddress(addressesReader));
        return new AccountProfile(userId, email, displayName, phone, addresses);
    }

    public async Task<CommerceWriteResult> UpdateProfileAsync(Guid userId,
        UpdateAccountProfile profile, CancellationToken cancellationToken)
    {
        const string sql = """
            WITH authorized AS MATERIALIZED (
                SELECT u.id FROM iam.users u
                JOIN iam.user_roles r ON r.user_id = u.id
                WHERE u.id = @user_id AND u.status = 'active'
                  AND r.role = 'customer' AND r.status = 'active'
            ), updated_user AS (
                UPDATE iam.users u SET display_name = @display_name, updated_at = now()
                FROM authorized a WHERE u.id = a.id RETURNING u.id
            )
            UPDATE iam.customer_profiles cp SET phone = @phone, updated_at = now()
            FROM updated_user u WHERE cp.user_id = u.id
            RETURNING cp.user_id
            """;
        await using var command = commerce.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("display_name", profile.DisplayName);
        command.Parameters.Add("phone", NpgsqlDbType.Text).Value = (object?)profile.Phone ?? DBNull.Value;
        return await command.ExecuteScalarAsync(cancellationToken) is Guid
            ? CommerceWriteResult.Updated : CommerceWriteResult.NotFound;
    }

    public async Task<CustomerAddress?> SaveAddressAsync(Guid userId, SaveCustomerAddress address,
        CancellationToken cancellationToken)
    {
        await using var connection = await commerce.DataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        const string authorizeSql = """
            SELECT EXISTS (
                SELECT 1 FROM iam.users u JOIN iam.user_roles r ON r.user_id = u.id
                WHERE u.id = @user_id AND u.status = 'active'
                  AND r.role = 'customer' AND r.status = 'active'
            )
            """;
        await using var authorize = new NpgsqlCommand(authorizeSql, connection, transaction);
        authorize.Parameters.AddWithValue("user_id", userId);
        if (await authorize.ExecuteScalarAsync(cancellationToken) is not true)
        {
            await transaction.RollbackAsync(cancellationToken);
            return null;
        }

        if (address.IsDefault)
        {
            const string resetSql = """
                UPDATE iam.customer_addresses SET is_default = false, updated_at = now()
                WHERE user_id = @user_id AND archived_at IS NULL AND is_default
                """;
            await using var reset = new NpgsqlCommand(resetSql, connection, transaction);
            reset.Parameters.AddWithValue("user_id", userId);
            await reset.ExecuteNonQueryAsync(cancellationToken);
        }

        var sql = address.AddressId is null
            ? """
              INSERT INTO iam.customer_addresses (
                  user_id, label, recipient_name, phone, address_line1, address_line2,
                  city, province, postal_code, is_default
              ) VALUES (
                  @user_id, @label, @recipient_name, @phone, @line1, @line2,
                  @city, @province, @postal_code, @is_default
              )
              RETURNING id, label, recipient_name, phone, address_line1, address_line2,
                        city, province, postal_code, is_default
              """
            : """
              UPDATE iam.customer_addresses SET
                  label = @label, recipient_name = @recipient_name, phone = @phone,
                  address_line1 = @line1, address_line2 = @line2, city = @city,
                  province = @province, postal_code = @postal_code,
                  is_default = @is_default, updated_at = now()
              WHERE id = @address_id AND user_id = @user_id AND archived_at IS NULL
              RETURNING id, label, recipient_name, phone, address_line1, address_line2,
                        city, province, postal_code, is_default
              """;
        await using var command = new NpgsqlCommand(sql, connection, transaction);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("label", address.Label);
        command.Parameters.AddWithValue("recipient_name", address.RecipientName);
        command.Parameters.AddWithValue("phone", address.Phone);
        command.Parameters.AddWithValue("line1", address.AddressLine1);
        AddNullableText(command, "line2", address.AddressLine2);
        command.Parameters.AddWithValue("city", address.City);
        AddNullableText(command, "province", address.Province);
        AddNullableText(command, "postal_code", address.PostalCode);
        command.Parameters.AddWithValue("is_default", address.IsDefault);
        if (address.AddressId is Guid addressId) command.Parameters.AddWithValue("address_id", addressId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            await transaction.RollbackAsync(cancellationToken);
            return null;
        }
        var saved = ReadAddress(reader);
        await reader.DisposeAsync();
        await transaction.CommitAsync(cancellationToken);
        return saved;
    }

    private static CustomerAddress ReadAddress(NpgsqlDataReader reader) => new(
        reader.GetGuid(0), reader.GetString(1), reader.GetString(2), reader.GetString(3),
        reader.GetString(4), reader.IsDBNull(5) ? null : reader.GetString(5), reader.GetString(6),
        reader.IsDBNull(7) ? null : reader.GetString(7),
        reader.IsDBNull(8) ? null : reader.GetString(8), reader.GetBoolean(9));

    private static void AddNullableText(NpgsqlCommand command, string name, string? value) =>
        command.Parameters.Add(name, NpgsqlDbType.Text).Value = (object?)value ?? DBNull.Value;
}

public sealed class UnavailableAccountStore : IAccountStore
{
    public Task<AccountProfile?> GetProfileAsync(Guid userId, CancellationToken cancellationToken) => Throw<AccountProfile?>();
    public Task<CommerceWriteResult> UpdateProfileAsync(Guid userId, UpdateAccountProfile profile,
        CancellationToken cancellationToken) => Throw<CommerceWriteResult>();
    public Task<CustomerAddress?> SaveAddressAsync(Guid userId, SaveCustomerAddress address,
        CancellationToken cancellationToken) => Throw<CustomerAddress?>();
    private static Task<T> Throw<T>() => Task.FromException<T>(new CommerceUnavailableException());
}
