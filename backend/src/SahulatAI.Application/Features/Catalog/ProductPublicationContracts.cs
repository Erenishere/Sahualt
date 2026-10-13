namespace SahulatAI.Application.Features.Catalog;

public interface IProductPublisher
{
    Task<bool> PublishAsync(Guid userId, Guid vendorId, Guid productId, CancellationToken cancellationToken);
}
