using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using SahulatAI.Application.Features.Marketplace;
using SahulatAI.Infrastructure.ML;

namespace SahulatAI.Api.Controllers;

[ApiController]
[Route("api/v1/catalog/search")]
public sealed class CatalogSearchController(ICatalogSearchService search) : ControllerBase
{
    [HttpGet]
    [EnableRateLimiting("public-read")]
    public async Task<IActionResult> Query([FromQuery] string? q, [FromQuery] string mode = "text",
        [FromQuery] string? category = null, [FromQuery] string? vendor = null,
        [FromQuery] int limit = 24, CancellationToken cancellationToken = default)
    {
        if (q?.Length > 200 || category?.Length > 100 || vendor?.Length > 200 || limit is < 1 or > 50)
            return BadRequest(new ProblemDetails { Title = "Invalid search request.", Status = 400 });
        var normalizedMode = mode.Trim().ToLowerInvariant();
        if (normalizedMode is not ("text" or "semantic" or "hybrid" or "keyword"))
            normalizedMode = "text";
        try
        {
            Response.Headers.CacheControl = "public, max-age=15";
            return Ok(await search.SearchAsync(q, normalizedMode, category, vendor, limit, cancellationToken));
        }
        catch (MlInferenceException)
        {
            return StatusCode(503, new ProblemDetails { Title = "Search service is unavailable.", Status = 503 });
        }
    }

    [HttpPost("image")]
    [EnableRateLimiting("public-read")]
    [RequestSizeLimit(22_000_000)]
    public async Task<IActionResult> Image([FromForm] IFormFile? image, [FromQuery] int limit = 24,
        CancellationToken cancellationToken = default)
    {
        if (image is null || image.Length is 0 or > 20_000_000)
            return BadRequest(new ProblemDetails { Title = "A valid image file is required.", Status = 400 });
        var mediaType = image.ContentType?.ToLowerInvariant();
        if (mediaType is not ("image/jpeg" or "image/png" or "image/webp"))
            return BadRequest(new ProblemDetails { Title = "Use JPEG, PNG, or WebP.", Status = 400 });
        await using var stream = image.OpenReadStream();
        using var memory = new MemoryStream();
        await stream.CopyToAsync(memory, cancellationToken);
        try
        {
            Response.Headers.CacheControl = "no-store";
            return Ok(await search.SearchByImageAsync(memory.ToArray(), mediaType, limit, cancellationToken));
        }
        catch (MlInferenceException)
        {
            return StatusCode(503, new ProblemDetails { Title = "Visual search is not configured.", Status = 503 });
        }
    }

    [HttpPost("voice")]
    [EnableRateLimiting("public-read")]
    [RequestSizeLimit(2_500_000)]
    public async Task<IActionResult> Voice([FromForm] IFormFile? audio, [FromQuery] string language = "en",
        [FromQuery] int limit = 24, CancellationToken cancellationToken = default)
    {
        if (audio is null || audio.Length is 0 or > 2_000_000)
            return BadRequest(new ProblemDetails { Title = "A valid audio file is required.", Status = 400 });
        if (language is not ("en" or "ur"))
            return BadRequest(new ProblemDetails { Title = "Language must be en or ur.", Status = 400 });
        await using var stream = audio.OpenReadStream();
        using var memory = new MemoryStream();
        await stream.CopyToAsync(memory, cancellationToken);
        try
        {
            Response.Headers.CacheControl = "no-store";
            return Ok(await search.SearchByVoiceAsync(memory.ToArray(), language, limit, cancellationToken));
        }
        catch (MlInferenceException)
        {
            return StatusCode(503, new ProblemDetails { Title = "Voice search is not configured.", Status = 503 });
        }
    }
}
