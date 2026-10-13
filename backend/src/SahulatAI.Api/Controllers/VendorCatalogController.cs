using System.Security.Claims;
using Amazon.S3;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Npgsql;
using SahulatAI.Application.Features.Assistant;
using SahulatAI.Application.Features.Catalog;
using SahulatAI.Api;

namespace SahulatAI.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/v1/vendors/{vendorId:guid}/catalog/products")]
public sealed class VendorCatalogController(
    IVendorAccessReader accessReader,
    IVendorCatalogReader catalogReader,
    IDraftProductWriter draftWriter,
    IProductVariantWriter variantWriter,
    IProductCategoryWriter categoryWriter,
    IProductImageWriter imageWriter,
    IProductImageReader imageReader,
    IProductPublisher publisher,
    IListingStockWriter stockWriter,
    IProductEditor productEditor) : ControllerBase
{
    [HttpPut("{productId:guid}")]
    [EnableRateLimiting("catalog-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> UpdateProduct(Guid vendorId, Guid productId,
        [FromBody] UpdateProductDetails? request, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (request is null || string.IsNullOrWhiteSpace(request.Name) || request.Name.Trim().Length > 200 ||
            string.IsNullOrWhiteSpace(request.Description) || request.Description.Trim().Length > 5000 ||
            request.Name.Any(char.IsControl) || request.Description.Any(char.IsControl))
            return BadRequest(new ProblemDetails { Title = "Name and description are required.", Status = 400 });
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId)) return Forbid();
        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken)) return NotFound();
        if (!await accessReader.CanManageCatalogAsync(userId, vendorId, cancellationToken)) return Forbid();
        try
        {
            var updated = await productEditor.UpdateProductAsync(userId, vendorId, productId,
                request with { Name = request.Name.Trim(), Description = request.Description.Trim() }, cancellationToken);
            return updated ? NoContent() : NotFound();
        }
        catch (CatalogWriteUnavailableException) { return WriterUnavailable(); }
    }

    [HttpPut("{productId:guid}/variants/{variantId:guid}")]
    [EnableRateLimiting("catalog-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> UpdateVariant(Guid vendorId, Guid productId, Guid variantId,
        [FromBody] UpdateVariantDetails? request, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (request is null || !ValidRequired(request.VariantCode, 80) || !ValidOptional(request.Sku, 200) ||
            !ValidOptional(request.Color, 100) || !ValidOptional(request.Size, 100))
            return BadRequest(new ProblemDetails { Title = "A valid variant code and optional SKU, color, and size are required.", Status = 400 });
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId)) return Forbid();
        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken)) return NotFound();
        if (!await accessReader.CanManageCatalogAsync(userId, vendorId, cancellationToken)) return Forbid();
        try
        {
            var updated = await productEditor.UpdateVariantAsync(userId, vendorId, productId, variantId,
                new UpdateVariantDetails(request.VariantCode.Trim(), TrimOrNull(request.Sku),
                    TrimOrNull(request.Color), TrimOrNull(request.Size)), cancellationToken);
            return updated ? NoContent() : NotFound();
        }
        catch (PostgresException error) when (error.SqlState == PostgresErrorCodes.UniqueViolation)
        {
            return Conflict(new ProblemDetails { Title = "That variant code is already in use.", Status = 409 });
        }
        catch (CatalogWriteUnavailableException) { return WriterUnavailable(); }
    }

    [HttpPut("{productId:guid}/listings/{listingId:guid}/commercial")]
    [EnableRateLimiting("catalog-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> UpdateCommercialDetails(Guid vendorId, Guid productId, Guid listingId,
        [FromBody] UpdateListingCommercialDetails? request, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (request is null || request.Price is <= 0 or > 10_000_000 || decimal.Round(request.Price, 2) != request.Price ||
            request.Currency is null || !System.Text.RegularExpressions.Regex.IsMatch(request.Currency, "^[A-Z]{3}$") ||
            request.Availability is not ("in_stock" or "out_of_stock" or "preorder" or "unavailable"))
            return BadRequest(new ProblemDetails { Title = "A positive price, ISO currency, and valid availability are required.", Status = 400 });
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId)) return Forbid();
        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken)) return NotFound();
        if (!await accessReader.CanManageCatalogAsync(userId, vendorId, cancellationToken)) return Forbid();
        try
        {
            var updated = await productEditor.UpdateListingAsync(userId, vendorId, productId, listingId,
                request, cancellationToken);
            return updated ? NoContent() : NotFound();
        }
        catch (CatalogWriteUnavailableException) { return WriterUnavailable(); }
    }
    [HttpPut("{productId:guid}/listings/{listingId:guid}/stock")]
    [EnableRateLimiting("catalog-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> SetStock(Guid vendorId, Guid productId, Guid listingId,
        [FromBody] SetListingStock? request, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (request is null || request.OnHandQuantity is < 0 or > 1_000_000 ||
            request.Availability is not ("in_stock" or "out_of_stock" or "preorder" or "unavailable") ||
            (request.OnHandQuantity == 0 && request.Availability == "in_stock"))
            return BadRequest(new ProblemDetails
            {
                Title = "Stock must be unknown or 0–1,000,000, with a valid availability. Zero stock cannot be in stock.",
                Status = 400
            });
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId))
            return Forbid();
        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken))
            return NotFound(new ProblemDetails { Title = "Vendor not found.", Status = 404 });
        if (!await accessReader.CanManageCatalogAsync(userId, vendorId, cancellationToken))
            return Forbid();

        try
        {
            var result = await stockWriter.SetAsync(userId, vendorId, productId, listingId,
                request, cancellationToken);
            return result switch
            {
                StockUpdateResult.Updated => NoContent(),
                StockUpdateResult.ListingNotFound => NotFound(new ProblemDetails
                    { Title = "Listing not found.", Status = 404 }),
                _ => Conflict(new ProblemDetails
                    { Title = "Stock is below the reserved quantity or the listing changed. Refresh and retry.", Status = 409 })
            };
        }
        catch (PostgresException error) when (error.SqlState == PostgresErrorCodes.CheckViolation)
        {
            return Conflict(new ProblemDetails
                { Title = "Stock conflicts with a current reservation. Refresh and retry.", Status = 409 });
        }
        catch (CatalogWriteUnavailableException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable,
                new ProblemDetails { Title = "Catalog editing is not configured.", Status = 503 });
        }
    }

    [HttpPost]
    [EnableRateLimiting("catalog-write")]
    [RequestSizeLimit(16_384)]
    [ProducesResponseType<DraftProduct>(StatusCodes.Status201Created)]
    public async Task<ActionResult<DraftProduct>> CreateDraft(
        Guid vendorId, [FromBody] CreateDraftProduct? request, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (request is null || request.Name is null || request.Description is null ||
            string.IsNullOrWhiteSpace(request.Name) || string.IsNullOrWhiteSpace(request.Description) ||
            request.Name.Trim().Length > 200 || request.Description.Trim().Length > 5000)
            return BadRequest(new ProblemDetails { Title = "Name (1–200) and description (1–5000) are required.", Status = 400 });
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId))
            return Forbid();
        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken))
            return NotFound(new ProblemDetails { Title = "Vendor not found.", Status = 404 });
        if (!await accessReader.CanManageCatalogAsync(userId, vendorId, cancellationToken))
            return Forbid();

        try
        {
            var product = await draftWriter.CreateAsync(userId, vendorId,
                new CreateDraftProduct(request.Name.Trim(), request.Description.Trim()), cancellationToken);
            if (product is null)
                return Conflict(new ProblemDetails { Title = "Vendor permissions changed. Retry after refreshing your session.", Status = 409 });
            return CreatedAtAction(nameof(GetProduct), new { vendorId, productId = product.ProductId }, product);
        }
        catch (CatalogWriteUnavailableException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable,
                new ProblemDetails { Title = "Catalog editing is not configured.", Status = 503 });
        }
    }

    [HttpGet("{productId:guid}/publication")]
    [EnableRateLimiting("assistant")]
    public async Task<ActionResult<PublicationFacts>> GetPublication(
        Guid vendorId, Guid productId, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId))
            return Forbid();
        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken))
            return NotFound();
        var facts = await catalogReader.GetPublicationFactsAsync(userId, vendorId, productId, cancellationToken);
        return facts is null ? NotFound() : Ok(facts);
    }

    [HttpPost("{productId:guid}/publish")]
    [EnableRateLimiting("catalog-write")]
    public async Task<IActionResult> Publish(Guid vendorId, Guid productId, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId))
            return Forbid();
        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken))
            return NotFound(new ProblemDetails { Title = "Vendor not found.", Status = 404 });
        if (!await accessReader.CanPublishCatalogAsync(userId, vendorId, cancellationToken))
            return Forbid();
        try
        {
            if (!await publisher.PublishAsync(userId, vendorId, productId, cancellationToken))
                return Conflict(new ProblemDetails
                {
                    Title = "The draft is missing publication requirements or has changed. Refresh and retry.",
                    Status = 409
                });
            return NoContent();
        }
        catch (CatalogWriteUnavailableException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable,
                new ProblemDetails { Title = "Catalog editing is not configured.", Status = 503 });
        }
    }

    [HttpPost("{productId:guid}/images")]
    [EnableRateLimiting("catalog-write")]
    [RequestSizeLimit(5_500_000)]
    [RequestFormLimits(MultipartBodyLengthLimit = 5_500_000)]
    [ProducesResponseType<UploadedProductImage>(StatusCodes.Status201Created)]
    public async Task<ActionResult<UploadedProductImage>> UploadImage(Guid vendorId, Guid productId,
        [FromForm] IFormFile? image, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (image is null || image.Length is < 33 or > 5_242_880)
            return BadRequest(new ProblemDetails { Title = "A JPEG or PNG image up to 5 MB is required.", Status = 400 });
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId))
            return Forbid();
        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken))
            return NotFound(new ProblemDetails { Title = "Vendor not found.", Status = 404 });
        if (!await accessReader.CanManageCatalogAsync(userId, vendorId, cancellationToken))
            return Forbid();

        using var buffer = new MemoryStream((int)image.Length);
        await image.CopyToAsync(buffer, cancellationToken);
        var bytes = buffer.ToArray();
        if (!ProductImageInspector.TryNormalize(bytes, out var normalized, out var mimeType,
                out var width, out var height))
            return BadRequest(new ProblemDetails { Title = "The image format or dimensions are invalid.", Status = 400 });
        try
        {
            var uploaded = await imageWriter.UploadAsync(userId, vendorId, productId, normalized,
                mimeType, width, height, cancellationToken);
            if (uploaded is null)
                return NotFound(new ProblemDetails { Title = "Draft product not found or vendor permissions changed.", Status = 404 });
            return CreatedAtAction(nameof(GetImage), new { vendorId, productId, imageId = uploaded.ImageId }, uploaded);
        }
        catch (PostgresException error) when (error.SqlState == PostgresErrorCodes.UniqueViolation)
        {
            return Conflict(new ProblemDetails { Title = "Image state changed. Refresh the product and retry.", Status = 409 });
        }
        catch (AmazonS3Exception)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable,
                new ProblemDetails { Title = "Image storage is unavailable.", Status = 503 });
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable,
                new ProblemDetails { Title = "Image storage is unavailable.", Status = 503 });
        }
        catch (ProductImageStoreUnavailableException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable,
                new ProblemDetails { Title = "Image storage is not configured.", Status = 503 });
        }
    }

    [HttpGet("{productId:guid}/images/{imageId:guid}")]
    [EnableRateLimiting("assistant")]
    public async Task<IActionResult> GetImage(Guid vendorId, Guid productId, Guid imageId,
        CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        Response.Headers.XContentTypeOptions = "nosniff";
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId))
            return Forbid();
        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken))
            return NotFound();
        try
        {
            var image = await imageReader.GetAsync(userId, vendorId, productId, imageId, cancellationToken);
            return image is null ? NotFound() : File(image.Bytes, image.MimeType);
        }
        catch (AmazonS3Exception)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable,
                new ProblemDetails { Title = "Image storage is unavailable.", Status = 503 });
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable,
                new ProblemDetails { Title = "Image storage is unavailable.", Status = 503 });
        }
        catch (ProductImageStoreUnavailableException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable,
                new ProblemDetails { Title = "Image storage is not configured.", Status = 503 });
        }
    }

    [HttpGet("/api/v1/vendors/{vendorId:guid}/catalog/categories")]
    [EnableRateLimiting("assistant")]
    public async Task<ActionResult<IReadOnlyList<CatalogCategory>>> GetCategories(
        Guid vendorId, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId))
            return Forbid();
        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken))
            return NotFound(new ProblemDetails { Title = "Vendor not found.", Status = 404 });
        return Ok(await catalogReader.GetActiveCategoriesAsync(userId, vendorId, cancellationToken));
    }

    [HttpPut("{productId:guid}/category")]
    [EnableRateLimiting("catalog-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> SetCategory(Guid vendorId, Guid productId,
        [FromBody] SetProductCategory? request, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (request is null || request.CategoryId == Guid.Empty)
            return BadRequest(new ProblemDetails { Title = "An active category is required.", Status = 400 });
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId))
            return Forbid();
        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken))
            return NotFound(new ProblemDetails { Title = "Vendor not found.", Status = 404 });
        if (!await accessReader.CanManageCatalogAsync(userId, vendorId, cancellationToken))
            return Forbid();
        try
        {
            if (!await categoryWriter.SetAsync(userId, vendorId, productId, request.CategoryId, cancellationToken))
                return NotFound(new ProblemDetails { Title = "Draft product or active category not found.", Status = 404 });
            return NoContent();
        }
        catch (CatalogWriteUnavailableException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable,
                new ProblemDetails { Title = "Catalog editing is not configured.", Status = 503 });
        }
    }

    [HttpPost("{productId:guid}/variants")]
    [EnableRateLimiting("catalog-write")]
    [RequestSizeLimit(16_384)]
    [ProducesResponseType<CreatedProductVariant>(StatusCodes.Status201Created)]
    public async Task<ActionResult<CreatedProductVariant>> CreateVariant(
        Guid vendorId, Guid productId, [FromBody] CreateProductVariant? request,
        CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (request is null || string.IsNullOrWhiteSpace(request.VariantCode) ||
            request.VariantCode.Trim().Length > 80 || request.Price <= 0 ||
            request.Price > 9_999_999_999.99m ||
            decimal.Round(request.Price, 2) != request.Price ||
            string.IsNullOrWhiteSpace(request.Currency) ||
            request.Currency.Length != 3 || request.Currency.Any(c => c is < 'A' or > 'Z') ||
            request.Availability is not ("in_stock" or "out_of_stock" or "preorder" or "unavailable"))
            return BadRequest(new ProblemDetails
            {
                Title = "A variant code, positive price, three-letter currency, and known availability are required.",
                Status = 400
            });
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId))
            return Forbid();
        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken))
            return NotFound(new ProblemDetails { Title = "Vendor not found.", Status = 404 });
        if (!await accessReader.CanManageCatalogAsync(userId, vendorId, cancellationToken))
            return Forbid();

        try
        {
            var variant = await variantWriter.CreateAsync(userId, vendorId, productId,
                request with { VariantCode = request.VariantCode.Trim() }, cancellationToken);
            if (variant is null)
                return NotFound(new ProblemDetails { Title = "Draft product not found or vendor permissions changed.", Status = 404 });
            return CreatedAtAction(nameof(GetProduct), new { vendorId, productId }, variant);
        }
        catch (PostgresException error) when (error.SqlState == PostgresErrorCodes.UniqueViolation)
        {
            return Conflict(new ProblemDetails { Title = "Variant code or default variant conflicts with a current record. Refresh and retry.", Status = 409 });
        }
        catch (CatalogWriteUnavailableException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable,
                new ProblemDetails { Title = "Catalog editing is not configured.", Status = 503 });
        }
    }

    [HttpGet]
    [EnableRateLimiting("assistant")]
    [ProducesResponseType<VendorCatalogPage>(StatusCodes.Status200OK)]
    public async Task<ActionResult<VendorCatalogPage>> GetProducts(
        Guid vendorId, [FromQuery] Guid? after, [FromQuery] int limit = 25,
        CancellationToken cancellationToken = default)
    {
        Response.Headers.CacheControl = "no-store";
        if (limit is < 1 or > 50)
            return BadRequest(new ProblemDetails { Title = "Limit must be between 1 and 50.", Status = 400 });
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId))
            return Forbid();
        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken))
            return NotFound(new ProblemDetails { Title = "Vendor not found.", Status = 404 });

        return Ok(await catalogReader.GetProductsAsync(userId, vendorId, after, limit, cancellationToken));
    }

    [HttpGet("{productId:guid}")]
    [EnableRateLimiting("assistant")]
    [ProducesResponseType<VendorProductDetails>(StatusCodes.Status200OK)]
    public async Task<ActionResult<VendorProductDetails>> GetProduct(
        Guid vendorId, Guid productId, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId))
            return Forbid();

        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken))
            return NotFound(new ProblemDetails { Title = "Product not found.", Status = 404 });

        var product = await catalogReader.GetProductDetailsAsync(userId, vendorId, productId, cancellationToken);
        if (product is null)
            return NotFound(new ProblemDetails { Title = "Product not found.", Status = 404 });

        return Ok(product);
    }

    private static bool ValidRequired(string? value, int max) =>
        value is not null && !string.IsNullOrWhiteSpace(value) && value.Trim().Length <= max && !value.Any(char.IsControl);
    private static bool ValidOptional(string? value, int max) =>
        value is null || (!string.IsNullOrWhiteSpace(value) && value.Trim().Length <= max && !value.Any(char.IsControl));
    private static string? TrimOrNull(string? value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    private ObjectResult WriterUnavailable() => StatusCode(StatusCodes.Status503ServiceUnavailable,
        new ProblemDetails { Title = "Catalog editing is not configured.", Status = 503 });
}
