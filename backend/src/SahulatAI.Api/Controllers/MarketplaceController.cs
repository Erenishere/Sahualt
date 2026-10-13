using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using SahulatAI.Application.Features.Marketplace;

namespace SahulatAI.Api.Controllers;

[ApiController]
[Route("api/v1/catalog/products")]
public sealed class MarketplaceController(IPublicCatalogReader catalog) : ControllerBase
{
    [HttpGet]
    [EnableRateLimiting("public-read")]
    public async Task<IActionResult> Search([FromQuery] string? query, [FromQuery] string? category,
        [FromQuery] string? vendor, [FromQuery] Guid? after, [FromQuery] int limit = 24,
        CancellationToken cancellationToken = default)
    {
        if (query?.Length > 200 || category?.Length > 100 || vendor?.Length > 200 || limit is < 1 or > 50)
            return BadRequest(new ProblemDetails { Title = "Invalid catalog search.", Status = 400 });
        Response.Headers.CacheControl = "public, max-age=30";
        return Ok(await catalog.SearchAsync(query, category, vendor, after, limit, cancellationToken));
    }

    [HttpGet("{productId:guid}")]
    [EnableRateLimiting("public-read")]
    public async Task<IActionResult> Get(Guid productId, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "public, max-age=30";
        var product = await catalog.GetAsync(productId, cancellationToken);
        return product is null
            ? NotFound(new ProblemDetails { Title = "Product not found.", Status = 404 })
            : Ok(product);
    }

    [HttpGet("{productId:guid}/images/{imageId:guid}")]
    [EnableRateLimiting("public-read")]
    public async Task<IActionResult> Image(Guid productId, Guid imageId,
        CancellationToken cancellationToken)
    {
        var image = await catalog.GetImageAsync(productId, imageId, cancellationToken);
        if (image is null) return NotFound();
        Response.Headers.CacheControl = "public, max-age=300";
        Response.Headers["X-Content-Type-Options"] = "nosniff";
        return File(image.Bytes, image.MimeType);
    }
}
