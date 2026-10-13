namespace SahulatAI.Application.Features.Admin;

public sealed record AdminUserRecord(
    Guid UserId, string Email, string DisplayName, string Status, DateTimeOffset CreatedAt,
    IReadOnlyList<string> Roles);

public sealed record AdminVendorRecord(
    Guid VendorId, string DisplayName, string Slug, string Status, DateTimeOffset CreatedAt,
    int ActiveMembers, int ProductCount);

public sealed record AdminActivityRecord(
    Guid ActivityId, string EntityType, Guid EntityId, string Action,
    Guid? VendorId, DateTimeOffset CreatedAt);

public sealed record AdminSummary(
    int RegisteredVendors, int ActiveListings, int RegisteredUsers, int PendingVendors,
    IReadOnlyList<AdminActivityRecord> RecentActivity);

public enum AdminWriteResult { Updated, NotFound, InvalidTransition }

public interface IAdminStore
{
    Task<AdminSummary?> GetSummaryAsync(Guid actorId, CancellationToken cancellationToken);
    Task<IReadOnlyList<AdminUserRecord>?> GetUsersAsync(Guid actorId, string? status, int limit,
        CancellationToken cancellationToken);
    Task<IReadOnlyList<AdminVendorRecord>?> GetVendorsAsync(Guid actorId, string? status, int limit,
        CancellationToken cancellationToken);
    Task<AdminWriteResult> UpdateUserStatusAsync(Guid actorId, Guid userId, string status,
        CancellationToken cancellationToken);
    Task<AdminWriteResult> UpdateVendorStatusAsync(Guid actorId, Guid vendorId, string status,
        CancellationToken cancellationToken);
}

public sealed class AdminUnavailableException : Exception { }
