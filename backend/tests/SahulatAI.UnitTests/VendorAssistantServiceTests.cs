using SahulatAI.Application.Features.Assistant;

namespace SahulatAI.UnitTests;

public sealed class VendorAssistantServiceTests
{
    private static readonly Guid VendorId = Guid.NewGuid();
    private static readonly Guid UserId = Guid.NewGuid();
    private static readonly Guid ProductId = Guid.NewGuid();
    private static readonly Guid ListingId = Guid.NewGuid();

    [Fact]
    public async Task SalesQuestionIsUnsupportedWithoutReadingCatalog()
    {
        var reader = new StubCatalogReader();
        var result = await new VendorAssistantService(reader, TimeProvider.System)
            .AnswerAsync(UserId, VendorId, new AssistantQuery("How much did I sell this month?"), default);

        Assert.Equal("unsupported", result.Outcome);
        Assert.Empty(result.Evidence);
        Assert.False(reader.WasCalled);
    }

    [Fact]
    public async Task LowStockAnswerIncludesCountAndListingEvidence()
    {
        var reader = new StubCatalogReader
        {
            Page = new ListingPage(1,
            [new ListingFact(ProductId, "Blue Kurta", ListingId, "active", 1200m, "PKR", "in_stock", 4, 1)])
        };
        var result = await new VendorAssistantService(reader, TimeProvider.System)
            .AnswerAsync(UserId, VendorId, new AssistantQuery("Which products are low in stock?"), default);

        Assert.Equal("low_stock", result.Intent);
        Assert.Equal("answered", result.Outcome);
        Assert.Contains("1 active listing", result.Answer);
        Assert.Equal(ListingId, Assert.Single(result.Evidence).EntityId);
        Assert.Equal(VendorId, reader.VendorId);
    }

    [Fact]
    public async Task ProductSpecificQuestionRequiresProductId()
    {
        var reader = new StubCatalogReader();
        var result = await new VendorAssistantService(reader, TimeProvider.System)
            .AnswerAsync(UserId, VendorId, new AssistantQuery("Why can't this listing be published?"), default);

        Assert.Equal("needs_clarification", result.Outcome);
        Assert.False(reader.WasCalled);
    }

    [Fact]
    public async Task DraftProductWithoutListingIsIncluded()
    {
        var reader = new StubCatalogReader
        {
            Products = new ProductPage(1, [new ProductFact(ProductId, "Unlisted Kurta")])
        };
        var result = await new VendorAssistantService(reader, TimeProvider.System)
            .AnswerAsync(UserId, VendorId, new AssistantQuery("Which products are still drafts?"), default);

        Assert.Equal("draft_products", result.Intent);
        Assert.Contains("Unlisted Kurta", result.Answer);
        Assert.Equal(ProductId, Assert.Single(result.Evidence).EntityId);
    }

    [Fact]
    public async Task PublicationAnswerNamesMissingRequirements()
    {
        var reader = new StubCatalogReader
        {
            Publication = new PublicationFacts(ProductId, "Blue Kurta", "draft", false, false, true, false)
        };
        var result = await new VendorAssistantService(reader, TimeProvider.System)
            .AnswerAsync(UserId, VendorId, new AssistantQuery("Why can't this product be published?", ProductId), default);

        Assert.Contains("active category is missing", result.Answer);
        Assert.Contains("active image is missing", result.Answer);
        Assert.Equal(ProductId, Assert.Single(result.Evidence).EntityId);
    }

    private sealed class StubCatalogReader : IVendorCatalogReader
    {
        public Task<VendorCatalogPage> GetProductsAsync(Guid userId, Guid vendorId, Guid? after, int limit,
            CancellationToken cancellationToken) => Task.FromResult(new VendorCatalogPage([], null));

        public Task<VendorProductDetails?> GetProductDetailsAsync(Guid userId, Guid vendorId, Guid productId,
            CancellationToken cancellationToken) => Task.FromResult<VendorProductDetails?>(null);

        public Task<IReadOnlyList<CatalogCategory>> GetActiveCategoriesAsync(Guid userId, Guid vendorId,
            CancellationToken cancellationToken) => Task.FromResult<IReadOnlyList<CatalogCategory>>([]);

        public ListingPage Page { get; init; } = new(0, []);
        public ProductPage Products { get; init; } = new(0, []);
        public PublicationFacts? Publication { get; init; }
        public Guid VendorId { get; private set; }
        public Guid UserId { get; private set; }
        public bool WasCalled { get; private set; }

        public Task<ProductPage> GetDraftProductsAsync(Guid userId, Guid vendorId, int limit,
            CancellationToken cancellationToken)
        {
            UserId = userId;
            VendorId = vendorId;
            WasCalled = true;
            return Task.FromResult(Products);
        }

        public Task<ListingPage> GetListingsAsync(Guid userId, Guid vendorId, CatalogQuestion question,
            Guid? productId, int lowStockThreshold, int limit, CancellationToken cancellationToken)
        {
            UserId = userId;
            VendorId = vendorId;
            WasCalled = true;
            return Task.FromResult(Page);
        }

        public Task<PublicationFacts?> GetPublicationFactsAsync(Guid userId, Guid vendorId, Guid productId,
            CancellationToken cancellationToken)
        {
            UserId = userId;
            VendorId = vendorId;
            WasCalled = true;
            return Task.FromResult(Publication);
        }
    }
}
