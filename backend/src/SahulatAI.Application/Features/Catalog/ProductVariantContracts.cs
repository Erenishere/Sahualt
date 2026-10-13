namespace SahulatAI.Application.Features.Catalog;

public sealed record CreateProductVariant(
    string VariantCode, decimal Price, string Currency, string Availability, bool AllowCustomerOffers = false);

public sealed record CreatedProductVariant(Guid VariantId, Guid ListingId);

public interface IProductVariantWriter
{
    Task<CreatedProductVariant?> CreateAsync(
        Guid userId, Guid vendorId, Guid productId, CreateProductVariant request, CancellationToken cancellationToken);
}
