using Npgsql;
using SahulatAI.Application.Features.Catalog;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresDraftProductWriter(CatalogWriterDataSource writer) : IDraftProductWriter
{
    public async Task<DraftProduct?> CreateAsync(
        Guid userId, Guid vendorId, CreateDraftProduct request, CancellationToken cancellationToken)
    {
        const string sql = """
            INSERT INTO catalog.products (
                vendor_id, name, description, status, created_by_user_id, updated_by_user_id
            )
            SELECT @vendor_id, @name, @description, 'draft', u.id, u.id
            FROM iam.users u
            JOIN iam.vendor_memberships m ON m.user_id = u.id
            JOIN catalog.vendors v ON v.id = m.vendor_id
            WHERE u.id = @user_id AND m.vendor_id = @vendor_id
              AND u.status = 'active' AND m.status = 'active' AND v.status = 'active'
              AND m.role IN ('owner', 'manager', 'staff')
            RETURNING id, name, status
            """;
        await using var command = writer.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("name", request.Name);
        command.Parameters.AddWithValue("description", request.Description);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken)
            ? new DraftProduct(reader.GetGuid(0), reader.GetString(1), reader.GetString(2))
            : null;
    }
}

public sealed class UnavailableDraftProductWriter : IDraftProductWriter
{
    public Task<DraftProduct?> CreateAsync(
        Guid userId, Guid vendorId, CreateDraftProduct request, CancellationToken cancellationToken) =>
        throw new CatalogWriteUnavailableException();
}

public sealed class CatalogWriterDataSource(NpgsqlDataSource dataSource) : IAsyncDisposable
{
    public NpgsqlDataSource DataSource { get; } = dataSource;

    public ValueTask DisposeAsync() => DataSource.DisposeAsync();
}
