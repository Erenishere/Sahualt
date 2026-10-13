namespace SahulatAI.Application.Features.Marketplace;

public sealed record CatalogSearchPage(
    string Mode,
    string? Query,
    IReadOnlyList<PublicProductSummary> Items,
    Guid? NextAfter);

public interface ICatalogSearchService
{
    Task<CatalogSearchPage> SearchAsync(
        string? query,
        string mode,
        string? category,
        string? vendorSlug,
        int limit,
        CancellationToken cancellationToken);

    Task<CatalogSearchPage> SearchByImageAsync(
        byte[] image,
        string mediaType,
        int limit,
        CancellationToken cancellationToken);

    Task<CatalogSearchPage> SearchByVoiceAsync(
        byte[] audio,
        string language,
        int limit,
        CancellationToken cancellationToken);
}
