namespace SahulatAI.Infrastructure.Persistence;

public interface IProductImageObjectStore
{
    Task PutAsync(string key, byte[] bytes, string mimeType, CancellationToken cancellationToken);
    Task<byte[]> GetAsync(string key, CancellationToken cancellationToken);
    Task DeleteAsync(string key, CancellationToken cancellationToken);
}
