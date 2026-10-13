using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using SahulatAI.Application.Features.Marketplace;

namespace SahulatAI.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/v1/vendors/{vendorId:guid}/settings")]
public sealed class VendorSettingsController(IVendorSettingsStore settings) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> Get(Guid vendorId, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (!TryUserId(out var userId)) return Forbid();
        try
        {
            var profile = await settings.GetAsync(userId, vendorId, cancellationToken);
            return profile is null ? NotFound() : Ok(profile);
        }
        catch (CommerceUnavailableException) { return Unavailable(); }
    }

    [HttpPut]
    [EnableRateLimiting("commerce-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> Update(Guid vendorId, [FromBody] UpdateVendorStoreProfile? request,
        CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (!TryUserId(out var userId)) return Forbid();
        if (request is null || string.IsNullOrWhiteSpace(request.DisplayName) ||
            request.DisplayName.Trim().Length > 200 || request.DisplayName.Any(char.IsControl) ||
            (request.Description is not null && (string.IsNullOrWhiteSpace(request.Description) ||
                request.Description.Trim().Length > 2000 || request.Description.Any(char.IsControl))))
            return BadRequest(new ProblemDetails { Title = "A valid store name and optional description are required.", Status = 400 });
        try
        {
            var result = await settings.UpdateAsync(userId, vendorId,
                new UpdateVendorStoreProfile(request.DisplayName.Trim(),
                    string.IsNullOrWhiteSpace(request.Description) ? null : request.Description.Trim(),
                    request.AllowCustomerOffers), cancellationToken);
            return result == CommerceWriteResult.Updated ? NoContent() : NotFound();
        }
        catch (CommerceUnavailableException) { return Unavailable(); }
    }

    private bool TryUserId(out Guid userId) => Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out userId);
    private ObjectResult Unavailable() => StatusCode(503,
        new ProblemDetails { Title = "Vendor settings are not configured.", Status = 503 });
}
