namespace SahulatAI.Application.Features.Auth;

public interface IUserAuthenticator
{
    Task<Guid?> AuthenticateAsync(string email, string password, CancellationToken cancellationToken);
}
