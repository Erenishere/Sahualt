using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Npgsql;
using SahulatAI.Application.Features.Marketplace;

namespace SahulatAI.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/v1")]
public sealed class CustomerCommerceController(ICommerceStore commerce) : ControllerBase
{
    private static readonly HashSet<string> OfferStatuses =
        ["pending", "countered", "accepted", "rejected", "withdrawn", "expired", "converted"];
    private static readonly HashSet<string> OrderStatuses =
        ["placed", "confirmed", "processing", "shipped", "completed", "cancelled"];

    [HttpGet("offers")]
    public async Task<IActionResult> GetOffers([FromQuery] string? status, [FromQuery] int limit = 50,
        CancellationToken cancellationToken = default)
    {
        if (!TryUserId(out var userId)) return Forbid();
        if (!ValidFilter(status, OfferStatuses) || limit is < 1 or > 100) return InvalidFilter();
        return await Invoke(async () => Ok(await commerce.GetCustomerOffersAsync(
            userId, Normalize(status), limit, cancellationToken)));
    }

    [HttpGet("offers/{offerId:guid}")]
    public async Task<IActionResult> GetOffer(Guid offerId, CancellationToken cancellationToken)
    {
        if (!TryUserId(out var userId)) return Forbid();
        return await Invoke(async () =>
        {
            var offer = await commerce.GetCustomerOfferAsync(userId, offerId, cancellationToken);
            return offer is null ? NotFound() : Ok(offer);
        });
    }

    [HttpPost("offers")]
    [EnableRateLimiting("commerce-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> CreateOffer([FromBody] CreateOffer? request,
        CancellationToken cancellationToken)
    {
        if (!TryUserId(out var userId)) return Forbid();
        if (request is null || request.ListingId == Guid.Empty || request.OfferedPrice <= 0 ||
            request.OfferedPrice > 10_000_000 || decimal.Round(request.OfferedPrice, 2) != request.OfferedPrice ||
            (request.Message is not null && (string.IsNullOrWhiteSpace(request.Message) ||
                                              request.Message.Trim().Length > 500 || request.Message.Any(char.IsControl))))
            return BadRequest(new ProblemDetails { Title = "A valid listing, price, and optional message are required.", Status = 400 });
        return await Invoke(async () =>
        {
            var created = await commerce.CreateOfferAsync(userId,
                request with { Message = Normalize(request.Message) }, cancellationToken);
            return created is null
                ? Conflict(new ProblemDetails { Title = "The listing is unavailable, the price is invalid, or an open offer already exists.", Status = 409 })
                : Created($"/api/v1/offers/{created.OfferId:D}", created);
        });
    }

    [HttpPost("offers/{offerId:guid}/withdraw")]
    [EnableRateLimiting("commerce-write")]
    public async Task<IActionResult> WithdrawOffer(Guid offerId, CancellationToken cancellationToken)
    {
        if (!TryUserId(out var userId)) return Forbid();
        return await Invoke(async () => WriteResult(
            await commerce.WithdrawOfferAsync(userId, offerId, cancellationToken), "Offer"));
    }

    [HttpPost("offers/{offerId:guid}/accept-counter")]
    [EnableRateLimiting("commerce-write")]
    public async Task<IActionResult> AcceptCounterOffer(Guid offerId, CancellationToken cancellationToken)
    {
        if (!TryUserId(out var userId)) return Forbid();
        return await Invoke(async () => WriteResult(
            await commerce.AcceptCounterOfferAsync(userId, offerId, cancellationToken), "Offer"));
    }

    [HttpGet("orders")]
    public async Task<IActionResult> GetOrders([FromQuery] string? status, [FromQuery] int limit = 50,
        CancellationToken cancellationToken = default)
    {
        if (!TryUserId(out var userId)) return Forbid();
        if (!ValidFilter(status, OrderStatuses) || limit is < 1 or > 100) return InvalidFilter();
        return await Invoke(async () => Ok(await commerce.GetCustomerOrdersAsync(
            userId, Normalize(status), limit, cancellationToken)));
    }

    [HttpGet("orders/{orderId:guid}")]
    public async Task<IActionResult> GetOrder(Guid orderId, CancellationToken cancellationToken)
    {
        if (!TryUserId(out var userId)) return Forbid();
        return await Invoke(async () =>
        {
            var order = await commerce.GetCustomerOrderAsync(userId, orderId, cancellationToken);
            return order is null ? NotFound() : Ok(order);
        });
    }

    [HttpPost("orders")]
    [EnableRateLimiting("commerce-write")]
    [RequestSizeLimit(32_768)]
    public async Task<IActionResult> PlaceOrder([FromBody] PlaceOrder? request,
        CancellationToken cancellationToken)
    {
        if (!TryUserId(out var userId)) return Forbid();
        if (!ValidOrder(request))
            return BadRequest(new ProblemDetails { Title = "Valid checkout items, delivery details, and cash_on_delivery are required.", Status = 400 });
        var normalized = request! with
        {
            Delivery = request.Delivery with
            {
                Name = request.Delivery.Name.Trim(), Phone = request.Delivery.Phone.Trim(),
                AddressLine1 = request.Delivery.AddressLine1.Trim(),
                AddressLine2 = Normalize(request.Delivery.AddressLine2), City = request.Delivery.City.Trim(),
                Province = Normalize(request.Delivery.Province), PostalCode = Normalize(request.Delivery.PostalCode)
            }
        };
        return await Invoke(async () =>
        {
            var order = await commerce.PlaceOrderAsync(userId, normalized, cancellationToken);
            return order is null
                ? Conflict(new ProblemDetails { Title = "Checkout changed or stock is insufficient. Refresh and retry.", Status = 409 })
                : Created($"/api/v1/orders/{order.OrderId:D}", order);
        });
    }

    [HttpPost("orders/{orderId:guid}/cancel")]
    [EnableRateLimiting("commerce-write")]
    public async Task<IActionResult> CancelOrder(Guid orderId, CancellationToken cancellationToken)
    {
        if (!TryUserId(out var userId)) return Forbid();
        return await Invoke(async () => WriteResult(
            await commerce.CancelCustomerOrderAsync(userId, orderId, cancellationToken), "Order"));
    }

    private async Task<IActionResult> Invoke(Func<Task<IActionResult>> action)
    {
        Response.Headers.CacheControl = "no-store";
        try { return await action(); }
        catch (CommerceUnavailableException)
        {
            return StatusCode(503, new ProblemDetails { Title = "Commerce is not configured.", Status = 503 });
        }
        catch (IdempotencyConflictException)
        {
            return Conflict(new ProblemDetails { Title = "That idempotency key was already used for a different checkout.", Status = 409 });
        }
        catch (PostgresException error) when (error.SqlState is PostgresErrorCodes.SerializationFailure or PostgresErrorCodes.UniqueViolation)
        {
            return Conflict(new ProblemDetails { Title = "The request conflicted with a concurrent change. Refresh and retry.", Status = 409 });
        }
    }

    private IActionResult WriteResult(CommerceWriteResult result, string entity) => result switch
    {
        CommerceWriteResult.Updated => NoContent(),
        CommerceWriteResult.NotFound => NotFound(new ProblemDetails { Title = $"{entity} not found.", Status = 404 }),
        _ => Conflict(new ProblemDetails { Title = $"{entity} cannot be changed from its current state.", Status = 409 })
    };

    private bool TryUserId(out Guid userId) => Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out userId);
    private static bool ValidFilter(string? value, HashSet<string> allowed) =>
        string.IsNullOrWhiteSpace(value) || allowed.Contains(value.Trim().ToLowerInvariant());
    private static string? Normalize(string? value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
    private BadRequestObjectResult InvalidFilter() => BadRequest(new ProblemDetails { Title = "Invalid filter or limit.", Status = 400 });

    private static bool ValidOrder(PlaceOrder? request)
    {
        if (request is null || request.IdempotencyKey == Guid.Empty || request.PaymentMethod != "cash_on_delivery" ||
            request.Items is null || request.Delivery is null || request.Items.Count is < 1 or > 20 ||
            request.Items.Select(x => x.ListingId).Distinct().Count() != request.Items.Count ||
            request.Items.Any(x => x.ListingId == Guid.Empty || x.Quantity is < 1 or > 100)) return false;
        var d = request.Delivery;
        return ValidText(d.Name, 200) && ValidText(d.Phone, 32, 7) && ValidText(d.AddressLine1, 300) &&
               ValidText(d.City, 100) && ValidOptional(d.AddressLine2, 300) && ValidOptional(d.Province, 100) &&
               ValidOptional(d.PostalCode, 20);
    }
    private static bool ValidText(string? value, int max, int min = 1) =>
        value is not null && value.Trim().Length >= min && value.Trim().Length <= max && !value.Any(char.IsControl);
    private static bool ValidOptional(string? value, int max) => value is null || ValidText(value, max);
}
