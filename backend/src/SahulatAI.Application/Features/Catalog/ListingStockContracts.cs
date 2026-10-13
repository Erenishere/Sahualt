namespace SahulatAI.Application.Features.Catalog;

public sealed record SetListingStock(int? OnHandQuantity, string Availability);

public enum StockUpdateResult
{
    Updated,
    ListingNotFound,
    Conflict
}

public interface IListingStockWriter
{
    Task<StockUpdateResult> SetAsync(Guid userId, Guid vendorId, Guid productId,
        Guid listingId, SetListingStock request, CancellationToken cancellationToken);
}
