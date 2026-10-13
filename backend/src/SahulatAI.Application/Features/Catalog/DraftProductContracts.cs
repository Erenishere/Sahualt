namespace SahulatAI.Application.Features.Catalog;

public sealed record CreateDraftProduct(string Name, string Description);

public sealed record DraftProduct(Guid ProductId, string ProductName, string ProductStatus);

public interface IDraftProductWriter
{
    Task<DraftProduct?> CreateAsync(
        Guid userId, Guid vendorId, CreateDraftProduct request, CancellationToken cancellationToken);
}

public sealed class CatalogWriteUnavailableException : Exception { }
