using Isopoh.Cryptography.Argon2;

namespace SahulatAI.UnitTests;

public sealed class PasswordHashContractTests
{
    [Fact]
    public void Argon2idHashMatchesExistingDatabaseContract()
    {
        var encoded = Argon2.Hash("test-only password");

        Assert.StartsWith("$argon2id$", encoded);
        Assert.True(Argon2.Verify(encoded, "test-only password"));
        Assert.False(Argon2.Verify(encoded, "wrong password"));
    }
}
