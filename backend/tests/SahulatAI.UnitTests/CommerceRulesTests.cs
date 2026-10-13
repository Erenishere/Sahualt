using SahulatAI.Application.Features.Marketplace;

namespace SahulatAI.UnitTests;

public sealed class CommerceRulesTests
{
    [Theory]
    [InlineData("placed", "confirmed")]
    [InlineData("confirmed", "processing")]
    [InlineData("processing", "shipped")]
    [InlineData("shipped", "completed")]
    [InlineData("placed", "cancelled")]
    [InlineData("confirmed", "cancelled")]
    [InlineData("processing", "cancelled")]
    public void VendorTransitions_AcceptDefinedForwardPaths(string current, string next) =>
        Assert.True(CommerceRules.CanVendorTransition(current, next));

    [Theory]
    [InlineData("placed", "shipped")]
    [InlineData("shipped", "cancelled")]
    [InlineData("completed", "cancelled")]
    [InlineData("cancelled", "confirmed")]
    public void VendorTransitions_RejectSkippedAndTerminalPaths(string current, string next) =>
        Assert.False(CommerceRules.CanVendorTransition(current, next));

    [Theory]
    [InlineData("placed", true)]
    [InlineData("confirmed", true)]
    [InlineData("processing", false)]
    [InlineData("shipped", false)]
    public void CustomerCancellation_IsBounded(string status, bool expected) =>
        Assert.Equal(expected, CommerceRules.CanCustomerCancel(status));

    [Theory]
    [InlineData(100, 80, 2, 40)]
    [InlineData(80, 100, 2, 0)]
    [InlineData(100, 100, 3, 0)]
    public void NegotiatedDiscount_NeverMakesCurrentPriceNegative(
        decimal current, decimal negotiated, int quantity, decimal expected) =>
        Assert.Equal(expected, CommerceRules.NegotiatedDiscount(current, negotiated, quantity));
}
