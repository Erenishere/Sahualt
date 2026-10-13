using SahulatAI.Api;
using SkiaSharp;

namespace SahulatAI.UnitTests;

public sealed class ProductImageInspectorTests
{
    [Fact]
    public void DecodesAndReencodesPngBeforeStorage()
    {
        using var bitmap = new SKBitmap(2, 2);
        bitmap.Erase(SKColors.Orange);
        using var image = SKImage.FromBitmap(bitmap);
        using var encoded = image.Encode(SKEncodedImageFormat.Png, 100);

        Assert.True(ProductImageInspector.TryNormalize(encoded.ToArray(),
            out var normalized, out var mimeType, out var width, out var height));
        Assert.Equal("image/png", mimeType);
        Assert.Equal(2, width);
        Assert.Equal(2, height);
        using var verified = SKBitmap.Decode(normalized);
        Assert.NotNull(verified);
    }

    [Fact]
    public void RejectsNonImageContent()
    {
        var html = System.Text.Encoding.UTF8.GetBytes("<svg><script>alert(1)</script></svg>");
        Assert.False(ProductImageInspector.TryNormalize(html, out _, out _, out _, out _));
    }
}
