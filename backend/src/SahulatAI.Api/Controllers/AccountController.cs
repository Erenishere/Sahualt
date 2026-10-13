using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Npgsql;
using SahulatAI.Application.Features.Marketplace;

namespace SahulatAI.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/v1/account")]
public sealed class AccountController(IAccountStore accounts) : ControllerBase
{
    [HttpGet("profile")]
    public async Task<IActionResult> GetProfile(CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (!TryUserId(out var userId)) return Forbid();
        try
        {
            var profile = await accounts.GetProfileAsync(userId, cancellationToken);
            return profile is null ? NotFound() : Ok(profile);
        }
        catch (CommerceUnavailableException) { return Unavailable(); }
    }

    [HttpPut("profile")]
    [EnableRateLimiting("commerce-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> UpdateProfile([FromBody] UpdateAccountProfile? request,
        CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (!TryUserId(out var userId)) return Forbid();
        if (request is null || !ValidRequired(request.DisplayName, 200) ||
            !ValidOptional(request.Phone, 32, 7)) return Invalid("A valid display name and optional phone are required.");
        try
        {
            var result = await accounts.UpdateProfileAsync(userId,
                new UpdateAccountProfile(request.DisplayName.Trim(), TrimOrNull(request.Phone)), cancellationToken);
            return result == CommerceWriteResult.Updated ? NoContent() : NotFound();
        }
        catch (CommerceUnavailableException) { return Unavailable(); }
    }

    [HttpPost("addresses")]
    [EnableRateLimiting("commerce-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> CreateAddress([FromBody] SaveCustomerAddress? request,
        CancellationToken cancellationToken) => await SaveAddress(request is null ? null : request with { AddressId = null }, cancellationToken);

    [HttpPut("addresses/{addressId:guid}")]
    [EnableRateLimiting("commerce-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> UpdateAddress(Guid addressId, [FromBody] SaveCustomerAddress? request,
        CancellationToken cancellationToken) => await SaveAddress(request is null ? null : request with { AddressId = addressId }, cancellationToken);

    private async Task<IActionResult> SaveAddress(SaveCustomerAddress? request, CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (!TryUserId(out var userId)) return Forbid();
        if (request is null || !ValidRequired(request.Label, 50) || !ValidRequired(request.RecipientName, 200) ||
            !ValidRequired(request.Phone, 32, 7) || !ValidRequired(request.AddressLine1, 300) ||
            !ValidRequired(request.City, 100) || !ValidOptional(request.AddressLine2, 300) ||
            !ValidOptional(request.Province, 100) || !ValidOptional(request.PostalCode, 20))
            return Invalid("A valid recipient, phone, and delivery address are required.");
        var normalized = request with
        {
            Label = request.Label.Trim(), RecipientName = request.RecipientName.Trim(), Phone = request.Phone.Trim(),
            AddressLine1 = request.AddressLine1.Trim(), AddressLine2 = TrimOrNull(request.AddressLine2),
            City = request.City.Trim(), Province = TrimOrNull(request.Province), PostalCode = TrimOrNull(request.PostalCode)
        };
        try
        {
            var saved = await accounts.SaveAddressAsync(userId, normalized, cancellationToken);
            return saved is null ? NotFound() : request.AddressId is null
                ? Created($"/api/v1/account/addresses/{saved.AddressId:D}", saved) : Ok(saved);
        }
        catch (CommerceUnavailableException) { return Unavailable(); }
        catch (PostgresException error) when (error.SqlState == PostgresErrorCodes.UniqueViolation)
        {
            return Conflict(new ProblemDetails { Title = "The address changed concurrently. Refresh and retry.", Status = 409 });
        }
    }

    private bool TryUserId(out Guid userId) => Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out userId);
    private static bool ValidRequired(string? value, int max, int min = 1) =>
        value is not null && value.Trim().Length >= min && value.Trim().Length <= max && !value.Any(char.IsControl);
    private static bool ValidOptional(string? value, int max, int min = 1) =>
        value is null || (value.Trim().Length >= min && value.Trim().Length <= max && !value.Any(char.IsControl));
    private static string? TrimOrNull(string? value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    private BadRequestObjectResult Invalid(string title) => BadRequest(new ProblemDetails { Title = title, Status = 400 });
    private ObjectResult Unavailable() => StatusCode(503, new ProblemDetails { Title = "Commerce is not configured.", Status = 503 });
}
