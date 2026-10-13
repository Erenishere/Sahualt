using System.Text.RegularExpressions;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class LocalProductImageStore(string rootPath) : IProductImageObjectStore
{
    private const int MaxBytes = 5 * 1024 * 1024;
    private readonly string root = Path.GetFullPath(rootPath);

    public async Task PutAsync(string key, byte[] bytes, string mimeType, CancellationToken cancellationToken)
    {
        if (bytes.Length > MaxBytes) throw new InvalidDataException("Product image exceeds the allowed size.");
        var path = Resolve(key);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temporaryPath = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            await using (var stream = new FileStream(temporaryPath, FileMode.CreateNew, FileAccess.Write,
                             FileShare.None, 64 * 1024, FileOptions.Asynchronous | FileOptions.WriteThrough))
            {
                await stream.WriteAsync(bytes, cancellationToken);
                await stream.FlushAsync(cancellationToken);
            }
            File.Move(temporaryPath, path);
        }
        finally
        {
            if (File.Exists(temporaryPath)) File.Delete(temporaryPath);
        }
    }

    public async Task<byte[]> GetAsync(string key, CancellationToken cancellationToken)
    {
        var path = Resolve(key);
        var size = new FileInfo(path).Length;
        if (size > MaxBytes) throw new InvalidDataException("Stored product image exceeds the allowed size.");
        var bytes = await File.ReadAllBytesAsync(path, cancellationToken);
        if (bytes.Length > MaxBytes) throw new InvalidDataException("Stored product image exceeds the allowed size.");
        return bytes;
    }

    public Task DeleteAsync(string key, CancellationToken cancellationToken)
    {
        File.Delete(Resolve(key));
        return Task.CompletedTask;
    }

    private string Resolve(string key)
    {
        var parts = key.Split('/');
        if (parts.Length != 5 || parts[0] != "vendors" || parts[2] != "products" ||
            !Guid.TryParseExact(parts[1], "D", out _) || !Guid.TryParseExact(parts[3], "D", out _) ||
            !Regex.IsMatch(parts[4], @"\A[0-9a-f]{32}\.(png|jpg)\z", RegexOptions.CultureInvariant))
            throw new InvalidDataException("Invalid product image storage key.");

        return Path.Combine(root, parts[0], parts[1], parts[2], parts[3], parts[4]);
    }
}
