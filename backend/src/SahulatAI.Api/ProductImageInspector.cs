using SkiaSharp;

namespace SahulatAI.Api;

public static class ProductImageInspector
{
    private const int MaxBytes = 5 * 1024 * 1024;
    private const int MaxDimension = 6000;
    private const int MaxPixels = 20_000_000;
    private static ReadOnlySpan<byte> PngSignature => [137, 80, 78, 71, 13, 10, 26, 10];

    public static bool TryNormalize(byte[] input, out byte[] normalized,
        out string mimeType, out int width, out int height)
    {
        normalized = [];
        mimeType = "";
        width = 0;
        height = 0;
        if (input.Length is < 33 or > MaxBytes) return false;

        var format = input.AsSpan().StartsWith(PngSignature)
            ? SKEncodedImageFormat.Png
            : input[0] == 0xFF && input[1] == 0xD8
                ? SKEncodedImageFormat.Jpeg
                : (SKEncodedImageFormat?)null;
        if (format is null) return false;

        using var source = new MemoryStream(input, writable: false);
        using var codec = SKCodec.Create(source);
        if (codec is null || codec.EncodedFormat != format) return false;
        width = codec.Info.Width;
        height = codec.Info.Height;
        if (width is < 1 or > MaxDimension || height is < 1 or > MaxDimension ||
            (long)width * height > MaxPixels) return false;

        using var bitmap = SKBitmap.Decode(codec);
        if (bitmap is null) return false;
        using var image = SKImage.FromBitmap(bitmap);
        using var encoded = image.Encode(format.Value, format == SKEncodedImageFormat.Jpeg ? 85 : 100);
        if (encoded is null || encoded.Size is < 33 or > MaxBytes) return false;
        normalized = encoded.ToArray();
        mimeType = format == SKEncodedImageFormat.Png ? "image/png" : "image/jpeg";
        return true;
    }
}
