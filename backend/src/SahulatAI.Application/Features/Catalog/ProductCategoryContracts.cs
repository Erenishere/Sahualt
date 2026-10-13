namespace SahulatAI.Application.Features.Catalog;

public sealed record SetProductCategory(Guid CategoryId);

public interface IProductCategoryWriter
{
    Task<bool> SetAsync(Guid userId, Guid vendorId, Guid productId, Guid categoryId,
        CancellationToken cancellationToken);
}
