namespace SahulatAI.Application.Features.Catalog;

public sealed record UpdateProductDetails(string Name, string Description, Guid? CategoryId);
public sealed record UpdateVariantDetails(string VariantCode, string? Sku, string? Color, string? Size);
public sealed record UpdateListingCommercialDetails(
    decimal Price, string Currency, string Availability, bool AllowCustomerOffers);

public interface IProductEditor
{
    Task<bool> UpdateProductAsync(Guid userId, Guid vendorId, Guid productId,
        UpdateProductDetails request, CancellationToken cancellationToken);
    Task<bool> UpdateVariantAsync(Guid userId, Guid vendorId, Guid productId, Guid variantId,
        UpdateVariantDetails request, CancellationToken cancellationToken);
    Task<bool> UpdateListingAsync(Guid userId, Guid vendorId, Guid productId, Guid listingId,
        UpdateListingCommercialDetails request, CancellationToken cancellationToken);
}
