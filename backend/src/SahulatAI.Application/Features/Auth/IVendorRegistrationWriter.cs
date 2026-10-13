namespace SahulatAI.Application.Features.Auth;

public sealed record VendorRegistration(string Email, string Password, string ContactName, string VendorName);

public interface IVendorRegistrationWriter
{
    Task RegisterAsync(VendorRegistration registration, CancellationToken cancellationToken);
}

public sealed class VendorRegistrationUnavailableException : Exception { }
