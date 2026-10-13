namespace SahulatAI.Application.Features.Auth;

public sealed record CustomerRegistration(string Email, string Password, string DisplayName, string? Phone);

public interface ICustomerRegistrationWriter
{
    Task RegisterAsync(CustomerRegistration registration, CancellationToken cancellationToken);
}

public sealed class CustomerRegistrationUnavailableException : Exception { }
