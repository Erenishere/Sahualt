using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using SahulatAI.Application.Features.Assistant;

namespace SahulatAI.Api.Controllers;

[ApiController]
[Authorize]
[EnableRateLimiting("assistant")]
[Route("api/v1/vendors/{vendorId:guid}/assistant")]
public sealed class VendorAssistantController(
    IVendorAccessReader accessReader,
    VendorAssistantService assistant) : ControllerBase
{
    public sealed record QueryRequest(string? Question, Guid? ProductId);

    [HttpPost("queries")]
    [ProducesResponseType<AssistantAnswer>(StatusCodes.Status200OK)]
    public async Task<ActionResult<AssistantAnswer>> Query(
        Guid vendorId,
        [FromBody] QueryRequest request,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(request.Question) || request.Question.Length > 500)
            return BadRequest(new ProblemDetails { Title = "Question must contain 1-500 characters.", Status = 400 });

        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId)) return Forbid();

        if (!await accessReader.HasActiveMembershipAsync(userId, vendorId, cancellationToken))
            return NotFound(new ProblemDetails { Title = "Vendor not found.", Status = 404 });

        var answer = await assistant.AnswerAsync(userId, vendorId,
            new AssistantQuery(request.Question, request.ProductId), cancellationToken);
        Response.Headers.CacheControl = "no-store";
        return Ok(answer);
    }
}
