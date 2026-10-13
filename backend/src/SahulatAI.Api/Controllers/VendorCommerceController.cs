using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Npgsql;
using SahulatAI.Application.Features.Marketplace;

namespace SahulatAI.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/v1/vendors/{vendorId:guid}/commerce")]
public sealed class VendorCommerceController(ICommerceStore commerce) : ControllerBase
{
    private static readonly HashSet<string> OfferStatuses =
        ["pending", "countered", "accepted", "rejected", "withdrawn", "expired", "converted"];
    private static readonly HashSet<string> OrderStatuses =
        ["placed", "confirmed", "processing", "shipped", "completed", "cancelled"];

    [HttpGet("summary")]
    public async Task<IActionResult> GetSummary(Guid vendorId, CancellationToken cancellationToken) =>
        await Invoke(async userId =>
        {
            var summary = await commerce.GetVendorSummaryAsync(userId, vendorId, cancellationToken);
            return summary is null ? NotFound() : Ok(summary);
        });

    [HttpGet("analytics")]
    public async Task<IActionResult> GetAnalytics(Guid vendorId, [FromQuery] int periodDays = 30,
        CancellationToken cancellationToken = default)
    {
        if (periodDays is not (7 or 30 or 90))
            return BadRequest(new ProblemDetails { Title = "Period must be 7, 30, or 90 days.", Status = 400 });
        return await Invoke(async userId =>
        {
            var analytics = await commerce.GetVendorAnalyticsAsync(userId, vendorId, periodDays, cancellationToken);
            return analytics is null ? NotFound() : Ok(analytics);
        });
    }

    [HttpGet("offers")]
    public async Task<IActionResult> GetOffers(Guid vendorId, [FromQuery] string? status,
        [FromQuery] int limit = 50, CancellationToken cancellationToken = default)
    {
        if (!ValidFilter(status, OfferStatuses) || limit is < 1 or > 100) return InvalidFilter();
        return await Invoke(async userId => Ok(await commerce.GetVendorOffersAsync(
            userId, vendorId, Normalize(status), limit, cancellationToken)));
    }

    public sealed record OfferDecisionRequest(string? Action, decimal? CounterPrice);

    [HttpPut("offers/{offerId:guid}/decision")]
    [EnableRateLimiting("commerce-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> DecideOffer(Guid vendorId, Guid offerId,
        [FromBody] OfferDecisionRequest? request, CancellationToken cancellationToken)
    {
        var action = request?.Action?.Trim().ToLowerInvariant();
        var counterPrice = request?.CounterPrice;
        var validCounterPrice = counterPrice is decimal price && price is > 0 and <= 10_000_000 &&
                                decimal.Round(price, 2) == price;
        if (action is not ("accept" or "counter" or "reject") ||
            (action == "counter" && !validCounterPrice) ||
            (action != "counter" && counterPrice is not null))
            return BadRequest(new ProblemDetails { Title = "Use accept, counter with a valid price, or reject.", Status = 400 });
        return await Invoke(async userId => Result(await commerce.DecideOfferAsync(
            userId, vendorId, offerId, new VendorOfferDecision(action, counterPrice), cancellationToken), "Offer"));
    }

    [HttpGet("orders")]
    public async Task<IActionResult> GetOrders(Guid vendorId, [FromQuery] string? status,
        [FromQuery] int limit = 50, CancellationToken cancellationToken = default)
    {
        if (!ValidFilter(status, OrderStatuses) || limit is < 1 or > 100) return InvalidFilter();
        return await Invoke(async userId => Ok(await commerce.GetVendorOrdersAsync(
            userId, vendorId, Normalize(status), limit, cancellationToken)));
    }

    public sealed record OrderStatusRequest(string? Status);

    [HttpPut("orders/{orderId:guid}/status")]
    [EnableRateLimiting("commerce-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> TransitionOrder(Guid vendorId, Guid orderId,
        [FromBody] OrderStatusRequest? request, CancellationToken cancellationToken)
    {
        var status = request?.Status?.Trim().ToLowerInvariant();
        if (status is not ("confirmed" or "processing" or "shipped" or "completed" or "cancelled"))
            return BadRequest(new ProblemDetails { Title = "Invalid next order status.", Status = 400 });
        return await Invoke(async userId => Result(await commerce.TransitionVendorOrderAsync(
            userId, vendorId, orderId, status, cancellationToken), "Order"));
    }

    private async Task<IActionResult> Invoke(Func<Guid, Task<IActionResult>> action)
    {
        Response.Headers.CacheControl = "no-store";
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId)) return Forbid();
        try { return await action(userId); }
        catch (CommerceUnavailableException)
        {
            return StatusCode(503, new ProblemDetails { Title = "Commerce is not configured.", Status = 503 });
        }
        catch (PostgresException error) when (error.SqlState == PostgresErrorCodes.SerializationFailure)
        {
            return Conflict(new ProblemDetails { Title = "The order changed concurrently. Refresh and retry.", Status = 409 });
        }
    }

    private IActionResult Result(CommerceWriteResult result, string entity) => result switch
    {
        CommerceWriteResult.Updated => NoContent(),
        CommerceWriteResult.NotFound => NotFound(new ProblemDetails { Title = $"{entity} not found.", Status = 404 }),
        _ => Conflict(new ProblemDetails { Title = $"{entity} cannot be changed from its current state.", Status = 409 })
    };
    private static bool ValidFilter(string? value, HashSet<string> allowed) =>
        string.IsNullOrWhiteSpace(value) || allowed.Contains(value.Trim().ToLowerInvariant());
    private static string? Normalize(string? value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim().ToLowerInvariant();
    private BadRequestObjectResult InvalidFilter() => BadRequest(new ProblemDetails { Title = "Invalid filter or limit.", Status = 400 });
}
