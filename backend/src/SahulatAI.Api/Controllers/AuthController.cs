using System.Security.Claims;
using System.Net.Mail;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using SahulatAI.Application.Features.Assistant;
using SahulatAI.Application.Features.Auth;

namespace SahulatAI.Api.Controllers;

[ApiController]
[Route("api/v1/auth")]
public sealed class AuthController(IUserAuthenticator authenticator, IVendorAccessReader accessReader,
    IVendorRegistrationWriter registrationWriter, ICustomerRegistrationWriter customerRegistrationWriter,
    IWebHostEnvironment environment) : ControllerBase
{
    public sealed record LoginRequest(string? Email, string? Password);
    public sealed record VendorRegistrationRequest(string? Email, string? Password,
        string? ContactName, string? VendorName);
    public sealed record CustomerRegistrationRequest(string? Email, string? Password,
        string? DisplayName, string? Phone);

    [HttpPost("customer-registrations")]
    [EnableRateLimiting("registration")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> RegisterCustomer([FromBody] CustomerRegistrationRequest request,
        CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (!environment.IsDevelopment()) return NotFound();

        var email = request.Email?.Trim();
        var displayName = request.DisplayName?.Trim();
        var phone = request.Phone?.Trim();
        if (string.IsNullOrEmpty(email) || email.Length > 254 || email.Any(c => c > 127) ||
            !MailAddress.TryCreate(email, out var parsedEmail) ||
            !string.Equals(parsedEmail.Address, email, StringComparison.OrdinalIgnoreCase) ||
            request.Password is null || request.Password.Length is < 12 or > 128 ||
            string.IsNullOrEmpty(displayName) || displayName.Length > 200 || displayName.Any(char.IsControl) ||
            (phone is not null && (phone.Length is < 7 or > 32 || phone.Any(char.IsControl))))
            return BadRequest(new ProblemDetails
            {
                Title = "Valid email, password (12-128 characters), display name, and optional phone are required.",
                Status = 400
            });

        try
        {
            await customerRegistrationWriter.RegisterAsync(
                new CustomerRegistration(email, request.Password, displayName, phone), cancellationToken);
        }
        catch (CustomerRegistrationUnavailableException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable,
                new ProblemDetails { Title = "Customer registration is not configured.", Status = 503 });
        }

        return Accepted(new { message = "If eligible, the account is ready for local sign-in." });
    }

    [HttpPost("vendor-registrations")]
    [EnableRateLimiting("registration")]
    [RequestSizeLimit(16_384)]
    public async Task<IActionResult> RegisterVendor([FromBody] VendorRegistrationRequest request,
        CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (!environment.IsDevelopment()) return NotFound();

        var email = request.Email?.Trim();
        var contactName = request.ContactName?.Trim();
        var vendorName = request.VendorName?.Trim();
        if (string.IsNullOrEmpty(email) || email.Length > 254 || email.Any(c => c > 127) ||
            !MailAddress.TryCreate(email, out var parsedEmail) ||
            !string.Equals(parsedEmail.Address, email, StringComparison.OrdinalIgnoreCase) ||
            request.Password is null || request.Password.Length is < 12 or > 128 ||
            string.IsNullOrEmpty(contactName) || contactName.Length > 200 ||
            contactName.Any(char.IsControl) ||
            string.IsNullOrEmpty(vendorName) || vendorName.Length > 200 ||
            vendorName.Any(char.IsControl))
            return BadRequest(new ProblemDetails
            {
                Title = "Valid email, password (12-128 characters), contact name, and vendor name are required.",
                Status = 400
            });

        try
        {
            await registrationWriter.RegisterAsync(
                new VendorRegistration(email, request.Password, contactName, vendorName), cancellationToken);
        }
        catch (VendorRegistrationUnavailableException)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable,
                new ProblemDetails { Title = "Vendor registration is not configured.", Status = 503 });
        }

        return Accepted(new { message = "If eligible, the registration is pending local review." });
    }

    [HttpPost("login")]
    [EnableRateLimiting("login")]
    public async Task<IActionResult> Login([FromBody] LoginRequest request, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(request.Email) || request.Email.Length > 254 ||
            string.IsNullOrEmpty(request.Password) || request.Password.Length > 1024)
            return BadRequest(new ProblemDetails { Title = "Invalid login request.", Status = 400 });

        var userId = await authenticator.AuthenticateAsync(request.Email, request.Password, cancellationToken);
        if (userId is null)
            return Unauthorized(new ProblemDetails { Title = "Invalid credentials.", Status = 401 });

        var claims = new[] { new Claim(ClaimTypes.NameIdentifier, userId.Value.ToString("D")) };
        var identity = new ClaimsIdentity(claims, CookieAuthenticationDefaults.AuthenticationScheme);
        await HttpContext.SignInAsync(
            CookieAuthenticationDefaults.AuthenticationScheme,
            new ClaimsPrincipal(identity),
            new AuthenticationProperties { IsPersistent = false });
        Response.Headers.CacheControl = "no-store";
        return Ok(new { userId });
    }

    [HttpGet("me")]
    [Authorize]
    public async Task<IActionResult> Me(CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        if (!Guid.TryParse(User.FindFirst(ClaimTypes.NameIdentifier)?.Value, out var userId) ||
            !await accessReader.IsActiveUserAsync(userId, cancellationToken))
            return Unauthorized();
        var vendors = await accessReader.GetActiveVendorsAsync(userId, cancellationToken);
        var roles = (await accessReader.GetActiveRolesAsync(userId, cancellationToken)).ToList();
        // The database keeps the explicit platform_admin capability name; the UI
        // receives the stable audience role alias used by its route guard.
        if (roles.Contains("platform_admin", StringComparer.Ordinal) &&
            !roles.Contains("admin", StringComparer.Ordinal))
            roles.Add("admin");
        return Ok(new { userId, roles, vendors });
    }

    [HttpPost("logout")]
    public async Task<IActionResult> Logout()
    {
        await HttpContext.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme);
        Response.Headers.CacheControl = "no-store";
        return NoContent();
    }
}
