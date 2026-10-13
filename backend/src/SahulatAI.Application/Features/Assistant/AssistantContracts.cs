namespace SahulatAI.Application.Features.Assistant;

public enum CatalogQuestion
{
    ActiveListings,
    DraftListings,
    DraftProducts,
    LowStock,
    UnknownStock,
    ListingDetails,
    PublicationBlockers
}

public sealed record AssistantQuery(string Question, Guid? ProductId = null);

public sealed record AssistantEvidence(
    string EntityType,
    Guid EntityId,
    string Label,
    DateTimeOffset ObservedAt,
    Guid ProductId);

public sealed record AssistantAnswer(
    string Answer,
    string Intent,
    string Outcome,
    IReadOnlyList<AssistantEvidence> Evidence,
    Guid CorrelationId);

public sealed record ListingFact(
    Guid ProductId,
    string ProductName,
    Guid ListingId,
    string ListingStatus,
    decimal? Price,
    string? Currency,
    string Availability,
    int? OnHandQuantity,
    int ReservedQuantity);

public sealed record ListingPage(int Total, IReadOnlyList<ListingFact> Items);

public sealed record ProductFact(Guid ProductId, string ProductName);

public sealed record ProductPage(int Total, IReadOnlyList<ProductFact> Items);

public sealed record VendorProductDetails(
    Guid ProductId,
    string ProductName,
    string Description,
    string ProductStatus,
    IReadOnlyList<ListingFact> Listings,
    bool HasMoreListings,
    Guid? CategoryId = null,
    IReadOnlyList<ProductImageFact>? Images = null);

public sealed record CatalogCategory(Guid CategoryId, string Name, Guid? ParentId);
public sealed record ProductImageFact(Guid ImageId, string MimeType, int? Width, int? Height, bool IsPrimary);

public sealed record PublicationFacts(
    Guid ProductId,
    string ProductName,
    string ProductStatus,
    bool HasCategory,
    bool HasActiveImage,
    bool HasActiveDefaultVariant,
    bool HasCompleteListing);

public sealed record VendorCatalogPage(IReadOnlyList<PublicationFacts> Items, Guid? NextAfter);

public interface IVendorCatalogReader
{
    Task<VendorCatalogPage> GetProductsAsync(
        Guid userId, Guid vendorId, Guid? after, int limit, CancellationToken cancellationToken);

    Task<VendorProductDetails?> GetProductDetailsAsync(
        Guid userId, Guid vendorId, Guid productId, CancellationToken cancellationToken);

    Task<IReadOnlyList<CatalogCategory>> GetActiveCategoriesAsync(
        Guid userId, Guid vendorId, CancellationToken cancellationToken);

    Task<ProductPage> GetDraftProductsAsync(Guid userId, Guid vendorId, int limit, CancellationToken cancellationToken);

    Task<ListingPage> GetListingsAsync(
        Guid userId,
        Guid vendorId,
        CatalogQuestion question,
        Guid? productId,
        int lowStockThreshold,
        int limit,
        CancellationToken cancellationToken);

    Task<PublicationFacts?> GetPublicationFactsAsync(
        Guid userId,
        Guid vendorId,
        Guid productId,
        CancellationToken cancellationToken);
}

public interface IVendorAccessReader
{
    Task<bool> IsActiveUserAsync(Guid userId, CancellationToken cancellationToken);
    Task<IReadOnlyList<string>> GetActiveRolesAsync(Guid userId, CancellationToken cancellationToken);
    Task<IReadOnlyList<VendorAccess>> GetActiveVendorsAsync(Guid userId, CancellationToken cancellationToken);
    Task<bool> HasActiveMembershipAsync(Guid userId, Guid vendorId, CancellationToken cancellationToken);
    Task<bool> CanManageCatalogAsync(Guid userId, Guid vendorId, CancellationToken cancellationToken);
    Task<bool> CanPublishCatalogAsync(Guid userId, Guid vendorId, CancellationToken cancellationToken);
}

public sealed record VendorAccess(Guid VendorId, string DisplayName, string Role);
