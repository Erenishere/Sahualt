using Amazon.S3;
using Amazon.S3.Model;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class S3ProductImageStore(IAmazonS3 client, string bucket) : IProductImageObjectStore
{
    public async Task PutAsync(string key, byte[] bytes, string mimeType, CancellationToken cancellationToken)
    {
        using var stream = new MemoryStream(bytes, writable: false);
        var request = new PutObjectRequest
        {
            BucketName = bucket,
            Key = key,
            InputStream = stream,
            ContentType = mimeType,
            AutoCloseStream = false
        };
        await client.PutObjectAsync(request, cancellationToken);
    }

    public async Task<byte[]> GetAsync(string key, CancellationToken cancellationToken)
    {
        using var response = await client.GetObjectAsync(bucket, key, cancellationToken);
        using var output = new MemoryStream();
        var buffer = new byte[64 * 1024];
        int read;
        while ((read = await response.ResponseStream.ReadAsync(buffer, cancellationToken)) > 0)
        {
            if (output.Length + read > 5 * 1024 * 1024)
                throw new InvalidDataException("Stored product image exceeds the allowed size.");
            await output.WriteAsync(buffer.AsMemory(0, read), cancellationToken);
        }
        return output.ToArray();
    }

    public async Task DeleteAsync(string key, CancellationToken cancellationToken) =>
        await client.DeleteObjectAsync(bucket, key, cancellationToken);
}
