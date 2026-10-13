namespace SahulatAI.Application.Features.Catalog;

public sealed record UploadedProductImage(Guid ImageId, string MimeType, int Width, int Height);

public sealed record ProductImageContent(byte[] Bytes, string MimeType);

public interface IProductImageWriter
{
    Task<UploadedProductImage?> UploadAsync(Guid userId, Guid vendorId, Guid productId,
        byte[] bytes, string mimeType, int width, int height, CancellationToken cancellationToken);
}

public interface IProductImageReader
{
    Task<ProductImageContent?> GetAsync(Guid userId, Guid vendorId, Guid productId,
        Guid imageId, CancellationToken cancellationToken);
}

public sealed class ProductImageStoreUnavailableException : Exception { }
