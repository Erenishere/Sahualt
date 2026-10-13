using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Npgsql;
using SahulatAI.Application.Features.Admin;

namespace SahulatAI.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/v1/admin")]
public sealed class AdminController(IAdminStore admin) : ControllerBase
{
    private static readonly HashSet<string> UserStatuses = ["pending", "active", "suspended", "archived"];
    private static readonly HashSet<string> VendorStatuses = ["pending", "active", "suspended", "archived"];
    public sealed record StatusRequest(string? Status);

    [HttpGet("summary")]
    public async Task<IActionResult> GetSummary(CancellationToken cancellationToken) =>
        await Invoke(async actorId =>
        {
            var summary = await admin.GetSummaryAsync(actorId, cancellationToken);
            return summary is null ? Forbid() : Ok(summary);
        });

    [HttpGet("users")]
    public async Task<IActionResult> GetUsers([FromQuery] string? status, [FromQuery] int limit = 100,
        CancellationToken cancellationToken = default)
    {
        if (!Valid(status, UserStatuses, limit)) return BadFilter();
        return await Invoke(async actorId =>
        {
            var users = await admin.GetUsersAsync(actorId, Normalize(status), limit, cancellationToken);
            return users is null ? Forbid() : Ok(users);
        });
    }

    [HttpPut("users/{userId:guid}/status")]
    [EnableRateLimiting("commerce-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> SetUserStatus(Guid userId, [FromBody] StatusRequest? request,
        CancellationToken cancellationToken)
    {
        var status = Normalize(request?.Status);
        if (status is null || !UserStatuses.Contains(status)) return BadFilter();
        return await Invoke(async actorId => Result(
            await admin.UpdateUserStatusAsync(actorId, userId, status, cancellationToken), "User"));
    }

    [HttpGet("vendors")]
    public async Task<IActionResult> GetVendors([FromQuery] string? status, [FromQuery] int limit = 100,
        CancellationToken cancellationToken = default)
    {
        if (!Valid(status, VendorStatuses, limit)) return BadFilter();
        return await Invoke(async actorId =>
        {
            var vendors = await admin.GetVendorsAsync(actorId, Normalize(status), limit, cancellationToken);
            return vendors is null ? Forbid() : Ok(vendors);
        });
    }

    [HttpPut("vendors/{vendorId:guid}/status")]
    [EnableRateLimiting("commerce-write")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> SetVendorStatus(Guid vendorId, [FromBody] StatusRequest? request,
        CancellationToken cancellationToken)
    {
        var status = Normalize(request?.Status);
        if (status is null || !VendorStatuses.Contains(status)) return BadFilter();
        return await Invoke(async actorId => Result(
            await admin.UpdateVendorStatusAsync(actorId, vendorId, status, cancellationToken), "Vendor"));
    }

    private async Task<IActionResult> Invoke(Func<Guid, Task<IActionResult>> action)
    {
        Response.Headers.CacheControl = "no-store";
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var actorId)) return Forbid();
        try { return await action(actorId); }
        catch (AdminUnavailableException)
        {
            return StatusCode(503, new ProblemDetails { Title = "Administration is not configured.", Status = 503 });
        }
        catch (PostgresException error) when (error.SqlState == PostgresErrorCodes.SerializationFailure)
        {
            return Conflict(new ProblemDetails { Title = "The record changed concurrently. Refresh and retry.", Status = 409 });
        }
    }
    private IActionResult Result(AdminWriteResult result, string entity) => result switch
    {
        AdminWriteResult.Updated => NoContent(),
        AdminWriteResult.NotFound => NotFound(new ProblemDetails { Title = $"{entity} not found.", Status = 404 }),
        _ => Conflict(new ProblemDetails { Title = "That status change is not allowed.", Status = 409 })
    };
    private static string? Normalize(string? value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim().ToLowerInvariant();
    private static bool Valid(string? status, HashSet<string> allowed, int limit) =>
        limit is >= 1 and <= 200 && (string.IsNullOrWhiteSpace(status) || allowed.Contains(Normalize(status)!));
    private BadRequestObjectResult BadFilter() => BadRequest(new ProblemDetails { Title = "Invalid status or limit.", Status = 400 });
}
