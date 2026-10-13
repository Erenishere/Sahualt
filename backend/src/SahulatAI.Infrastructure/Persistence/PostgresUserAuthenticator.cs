using Isopoh.Cryptography.Argon2;
using Npgsql;
using SahulatAI.Application.Features.Auth;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresUserAuthenticator(IdentityDataSource identityDataSource) : IUserAuthenticator
{
    public async Task<Guid?> AuthenticateAsync(
        string email, string password, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT id, password_hash FROM iam.users
            WHERE email_normalized = @email AND status = 'active' AND email_verified_at IS NOT NULL
            """;
        await using var command = identityDataSource.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("email", email.Trim().ToLowerInvariant());
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) return null;

        var userId = reader.GetGuid(0);
        var encodedHash = reader.GetString(1);
        if (!encodedHash.StartsWith("$argon2id$", StringComparison.Ordinal)) return null;
        return Argon2.Verify(encodedHash, password) ? userId : null;
    }
}

public sealed class IdentityDataSource(NpgsqlDataSource dataSource) : IAsyncDisposable
{
    public NpgsqlDataSource DataSource { get; } = dataSource;

    public ValueTask DisposeAsync() => DataSource.DisposeAsync();
}
