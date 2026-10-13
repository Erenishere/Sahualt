using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using SahulatAI.Application.Features.Assistant;
using SahulatAI.Application.Features.Auth;
using SahulatAI.Application.Features.Catalog;

namespace SahulatAI.UnitTests;

public sealed class VendorAssistantApiTests
{
    private static readonly Guid UserId = Guid.NewGuid();
    private static readonly Guid VendorId = Guid.NewGuid();
    private static readonly Guid ProductId = Guid.NewGuid();
    private const string FrontendOrigin = "http://localhost:3000";

    [Fact]
    public async Task AssistantRequiresSessionAndAllowedOrigin()
    {
        using var factory = new Factory();
        using var client = factory.CreateClient();
        var path = $"/api/v1/vendors/{VendorId}/assistant/queries";

        using var noOrigin = await client.PostAsJsonAsync(path, new { question = "Show my active listings" });
        Assert.Equal(HttpStatusCode.Forbidden, noOrigin.StatusCode);

        using var request = new HttpRequestMessage(HttpMethod.Post, path)
        {
            Content = JsonContent.Create(new { question = "Show my active listings" })
        };
        request.Headers.Add("Origin", FrontendOrigin);
        using var noSession = await client.SendAsync(request);
        Assert.Equal(HttpStatusCode.Unauthorized, noSession.StatusCode);
    }

    [Fact]
    public async Task LoginAndVendorMembershipGateAssistantData()
    {
        using var factory = new Factory();
        using var client = factory.CreateClient();
        using var login = new HttpRequestMessage(HttpMethod.Post, "/api/v1/auth/login")
        {
            Content = JsonContent.Create(new { email = "owner@example.test", password = "test-password" })
        };
        login.Headers.Add("Origin", FrontendOrigin);
        using var loginResponse = await client.SendAsync(login);
        Assert.Equal(HttpStatusCode.OK, loginResponse.StatusCode);

        using var allowed = new HttpRequestMessage(HttpMethod.Post,
            $"/api/v1/vendors/{VendorId}/assistant/queries")
        {
            Content = JsonContent.Create(new { question = "Show my active listings" })
        };
        allowed.Headers.Add("Origin", FrontendOrigin);
        using var allowedResponse = await client.SendAsync(allowed);
        Assert.Equal(HttpStatusCode.OK, allowedResponse.StatusCode);
        var answer = await allowedResponse.Content.ReadFromJsonAsync<AssistantAnswer>();
        Assert.Equal("active_listings", answer?.Intent);

        using var otherVendor = new HttpRequestMessage(HttpMethod.Post,
            $"/api/v1/vendors/{Guid.NewGuid()}/assistant/queries")
        {
            Content = JsonContent.Create(new { question = "Show my active listings" })
        };
        otherVendor.Headers.Add("Origin", FrontendOrigin);
        using var otherResponse = await client.SendAsync(otherVendor);
        Assert.Equal(HttpStatusCode.NotFound, otherResponse.StatusCode);
    }

    [Fact]
    public async Task ProductEvidenceRequiresCurrentVendorMembership()
    {
        using var factory = new Factory();
        using var client = factory.CreateClient();
        var path = $"/api/v1/vendors/{VendorId}/catalog/products/{ProductId}";

        using var anonymous = await client.GetAsync(path);
        Assert.Equal(HttpStatusCode.Unauthorized, anonymous.StatusCode);

        using var login = new HttpRequestMessage(HttpMethod.Post, "/api/v1/auth/login")
        {
            Content = JsonContent.Create(new { email = "owner@example.test", password = "test-password" })
        };
        login.Headers.Add("Origin", FrontendOrigin);
        using var loginResponse = await client.SendAsync(login);
        Assert.Equal(HttpStatusCode.OK, loginResponse.StatusCode);

        using var allowed = await client.GetAsync(path);
        Assert.Equal(HttpStatusCode.OK, allowed.StatusCode);
        Assert.Equal("no-store", allowed.Headers.CacheControl?.ToString());
        var product = await allowed.Content.ReadFromJsonAsync<VendorProductDetails>();
        Assert.Equal(ProductId, product?.ProductId);

        using var otherProduct = await client.GetAsync($"/api/v1/vendors/{VendorId}/catalog/products/{Guid.NewGuid()}");
        Assert.Equal(HttpStatusCode.NotFound, otherProduct.StatusCode);

        using var otherVendor = await client.GetAsync($"/api/v1/vendors/{Guid.NewGuid()}/catalog/products/{ProductId}");
        Assert.Equal(HttpStatusCode.NotFound, otherVendor.StatusCode);

        ((FakeAccessReader)factory.Services.GetRequiredService<IVendorAccessReader>()).MembershipActive = false;
        using var afterRevocation = await client.GetAsync(path);
        Assert.Equal(HttpStatusCode.NotFound, afterRevocation.StatusCode);
    }

    [Fact]
    public async Task CatalogPageRequiresMembershipAndBoundsPageSize()
    {
        using var factory = new Factory();
        using var client = factory.CreateClient();
        var path = $"/api/v1/vendors/{VendorId}/catalog/products";
        using var anonymous = await client.GetAsync(path);
        Assert.Equal(HttpStatusCode.Unauthorized, anonymous.StatusCode);

        using var login = new HttpRequestMessage(HttpMethod.Post, "/api/v1/auth/login")
        { Content = JsonContent.Create(new { email = "owner@example.test", password = "test-password" }) };
        login.Headers.Add("Origin", FrontendOrigin);
        using var loginResponse = await client.SendAsync(login);
        Assert.Equal(HttpStatusCode.OK, loginResponse.StatusCode);

        using var pageResponse = await client.GetAsync(path + "?limit=25");
        Assert.Equal(HttpStatusCode.OK, pageResponse.StatusCode);
        Assert.Equal("no-store", pageResponse.Headers.CacheControl?.ToString());
        var page = await pageResponse.Content.ReadFromJsonAsync<VendorCatalogPage>();
        Assert.Equal(ProductId, Assert.Single(page!.Items).ProductId);

        using var invalid = await client.GetAsync(path + "?limit=51");
        Assert.Equal(HttpStatusCode.BadRequest, invalid.StatusCode);
        using var otherVendor = await client.GetAsync($"/api/v1/vendors/{Guid.NewGuid()}/catalog/products");
        Assert.Equal(HttpStatusCode.NotFound, otherVendor.StatusCode);

        ((FakeAccessReader)factory.Services.GetRequiredService<IVendorAccessReader>()).MembershipActive = false;
        using var revoked = await client.GetAsync(path);
        Assert.Equal(HttpStatusCode.NotFound, revoked.StatusCode);
    }

    [Fact]
    public async Task DraftCreationRequiresEditorRoleAndAllowedOrigin()
    {
        using var factory = new Factory();
        using var client = factory.CreateClient();
        var path = $"/api/v1/vendors/{VendorId}/catalog/products";
        using var anonymous = new HttpRequestMessage(HttpMethod.Post, path)
        { Content = JsonContent.Create(new { name = "Blue Kurta", description = "Cotton kurta" }) };
        anonymous.Headers.Add("Origin", FrontendOrigin);
        using var anonymousResponse = await client.SendAsync(anonymous);
        Assert.Equal(HttpStatusCode.Unauthorized, anonymousResponse.StatusCode);

        using var login = new HttpRequestMessage(HttpMethod.Post, "/api/v1/auth/login")
        { Content = JsonContent.Create(new { email = "owner@example.test", password = "test-password" }) };
        login.Headers.Add("Origin", FrontendOrigin);
        using var loginResponse = await client.SendAsync(login);
        Assert.Equal(HttpStatusCode.OK, loginResponse.StatusCode);

        using var noOrigin = await client.PostAsJsonAsync(path,
            new { name = "Blue Kurta", description = "Cotton kurta" });
        Assert.Equal(HttpStatusCode.Forbidden, noOrigin.StatusCode);

        var access = (FakeAccessReader)factory.Services.GetRequiredService<IVendorAccessReader>();
        access.CanEdit = false;
        using var viewerRequest = new HttpRequestMessage(HttpMethod.Post, path)
        { Content = JsonContent.Create(new { name = "Blue Kurta", description = "Cotton kurta" }) };
        viewerRequest.Headers.Add("Origin", FrontendOrigin);
        using var viewerResponse = await client.SendAsync(viewerRequest);
        Assert.Equal(HttpStatusCode.Forbidden, viewerResponse.StatusCode);
        access.CanEdit = true;

        using var invalidRequest = new HttpRequestMessage(HttpMethod.Post, path)
        { Content = JsonContent.Create(new { name = " ", description = "Cotton kurta" }) };
        invalidRequest.Headers.Add("Origin", FrontendOrigin);
        using var invalidResponse = await client.SendAsync(invalidRequest);
        Assert.Equal(HttpStatusCode.BadRequest, invalidResponse.StatusCode);

        using var create = new HttpRequestMessage(HttpMethod.Post, path)
        { Content = JsonContent.Create(new { name = " Blue Kurta ", description = " Cotton kurta " }) };
        create.Headers.Add("Origin", FrontendOrigin);
        using var created = await client.SendAsync(create);
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        Assert.Equal("no-store", created.Headers.CacheControl?.ToString());
        Assert.Equal(new Uri(client.BaseAddress!, $"/api/v1/vendors/{VendorId}/catalog/products/{ProductId}"),
            created.Headers.Location);
        var product = await created.Content.ReadFromJsonAsync<DraftProduct>();
        Assert.Equal("draft", product?.ProductStatus);
        Assert.Equal("Blue Kurta", ((FakeDraftProductWriter)factory.Services.GetRequiredService<IDraftProductWriter>()).LastRequest?.Name);
    }

    [Fact]
    public async Task DraftCreationIsUnavailableWithoutWriterConfiguration()
    {
        using var factory = new Factory(enableWriter: false);
        using var client = factory.CreateClient();
        using var login = new HttpRequestMessage(HttpMethod.Post, "/api/v1/auth/login")
        { Content = JsonContent.Create(new { email = "owner@example.test", password = "test-password" }) };
        login.Headers.Add("Origin", FrontendOrigin);
        using var loginResponse = await client.SendAsync(login);
        Assert.Equal(HttpStatusCode.OK, loginResponse.StatusCode);

        using var create = new HttpRequestMessage(HttpMethod.Post,
            $"/api/v1/vendors/{VendorId}/catalog/products")
        { Content = JsonContent.Create(new { name = "Blue Kurta", description = "Cotton kurta" }) };
        create.Headers.Add("Origin", FrontendOrigin);
        using var unavailable = await client.SendAsync(create);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, unavailable.StatusCode);

        using var catalog = await client.GetAsync($"/api/v1/vendors/{VendorId}/catalog/products");
        Assert.Equal(HttpStatusCode.OK, catalog.StatusCode);
    }

    [Fact]
    public async Task VariantCreationRequiresEditorAndValidCommercialFields()
    {
        using var factory = new Factory();
        using var client = factory.CreateClient();
        var path = $"/api/v1/vendors/{VendorId}/catalog/products/{ProductId}/variants";
        using var login = new HttpRequestMessage(HttpMethod.Post, "/api/v1/auth/login")
        { Content = JsonContent.Create(new { email = "owner@example.test", password = "test-password" }) };
        login.Headers.Add("Origin", FrontendOrigin);
        using var loginResponse = await client.SendAsync(login);
        Assert.Equal(HttpStatusCode.OK, loginResponse.StatusCode);

        using var noOrigin = await client.PostAsJsonAsync(path,
            new { variantCode = "black-medium", price = 1999.00m, currency = "PKR", availability = "in_stock" });
        Assert.Equal(HttpStatusCode.Forbidden, noOrigin.StatusCode);

        var access = (FakeAccessReader)factory.Services.GetRequiredService<IVendorAccessReader>();
        access.CanEdit = false;
        using var viewerRequest = VariantRequest(path, 1999.00m);
        using var viewerResponse = await client.SendAsync(viewerRequest);
        Assert.Equal(HttpStatusCode.Forbidden, viewerResponse.StatusCode);
        access.CanEdit = true;

        using var invalidRequest = VariantRequest(path, 0m);
        using var invalidResponse = await client.SendAsync(invalidRequest);
        Assert.Equal(HttpStatusCode.BadRequest, invalidResponse.StatusCode);

        using var otherVendorRequest = VariantRequest(
            $"/api/v1/vendors/{Guid.NewGuid()}/catalog/products/{ProductId}/variants", 1999.00m);
        using var otherVendorResponse = await client.SendAsync(otherVendorRequest);
        Assert.Equal(HttpStatusCode.NotFound, otherVendorResponse.StatusCode);

        using var create = VariantRequest(path, 1999.00m);
        using var created = await client.SendAsync(create);
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        Assert.Equal("no-store", created.Headers.CacheControl?.ToString());
        Assert.Equal(new Uri(client.BaseAddress!, $"/api/v1/vendors/{VendorId}/catalog/products/{ProductId}"),
            created.Headers.Location);
        var writer = (FakeProductVariantWriter)factory.Services.GetRequiredService<IProductVariantWriter>();
        Assert.Equal("black-medium", writer.LastRequest?.VariantCode);
    }

    [Fact]
    public async Task PublicationRequiresOwnerOrManager()
    {
        using var factory = new Factory();
        using var client = factory.CreateClient();
        using var login = new HttpRequestMessage(HttpMethod.Post, "/api/v1/auth/login")
        { Content = JsonContent.Create(new { email = "owner@example.test", password = "test-password" }) };
        login.Headers.Add("Origin", FrontendOrigin);
        using var loginResponse = await client.SendAsync(login);
        Assert.Equal(HttpStatusCode.OK, loginResponse.StatusCode);

        var path = $"/api/v1/vendors/{VendorId}/catalog/products/{ProductId}/publish";
        using var noOrigin = await client.PostAsync(path, null);
        Assert.Equal(HttpStatusCode.Forbidden, noOrigin.StatusCode);

        var access = (FakeAccessReader)factory.Services.GetRequiredService<IVendorAccessReader>();
        access.CanPublish = false;
        using var staff = new HttpRequestMessage(HttpMethod.Post, path);
        staff.Headers.Add("Origin", FrontendOrigin);
        using var staffResponse = await client.SendAsync(staff);
        Assert.Equal(HttpStatusCode.Forbidden, staffResponse.StatusCode);

        access.CanPublish = true;
        using var publish = new HttpRequestMessage(HttpMethod.Post, path);
        publish.Headers.Add("Origin", FrontendOrigin);
        using var published = await client.SendAsync(publish);
        Assert.Equal(HttpStatusCode.NoContent, published.StatusCode);
        Assert.Equal("no-store", published.Headers.CacheControl?.ToString());
    }

    private static HttpRequestMessage VariantRequest(string path, decimal price)
    {
        var request = new HttpRequestMessage(HttpMethod.Post, path)
        {
            Content = JsonContent.Create(new
            {
                variantCode = " black-medium ", price, currency = "PKR", availability = "in_stock"
            })
        };
        request.Headers.Add("Origin", FrontendOrigin);
        return request;
    }

    private sealed class Factory : WebApplicationFactory<Program>
    {
        private readonly bool _enableWriter;

        public Factory(bool enableWriter = true) => _enableWriter = enableWriter;

        protected override void ConfigureWebHost(IWebHostBuilder builder)
        {
            builder.UseEnvironment("Development");
            builder.UseSetting("ConnectionStrings:AssistantReader", "Host=localhost;Username=assistant_test;Database=sahulat_test");
            builder.UseSetting("ConnectionStrings:IdentityReader", "Host=localhost;Username=identity_test;Database=sahulat_test");
            builder.UseSetting("Frontend:Origin", FrontendOrigin);
            builder.ConfigureTestServices(services =>
            {
                services.RemoveAll<IUserAuthenticator>();
                services.RemoveAll<IVendorAccessReader>();
                services.RemoveAll<IVendorCatalogReader>();
                services.AddSingleton<IUserAuthenticator>(new FakeAuthenticator());
                services.AddSingleton<IVendorAccessReader>(new FakeAccessReader());
                services.AddSingleton<IVendorCatalogReader>(new FakeCatalogReader());
                if (_enableWriter)
                {
                    services.RemoveAll<IDraftProductWriter>();
                    services.AddSingleton<IDraftProductWriter>(new FakeDraftProductWriter());
                    services.RemoveAll<IProductVariantWriter>();
                    services.AddSingleton<IProductVariantWriter>(new FakeProductVariantWriter());
                    services.RemoveAll<IProductCategoryWriter>();
                    services.AddSingleton<IProductCategoryWriter>(new FakeProductCategoryWriter());
                    services.RemoveAll<IProductPublisher>();
                    services.AddSingleton<IProductPublisher>(new FakeProductPublisher());
                }
            });
        }
    }

    private sealed class FakeAuthenticator : IUserAuthenticator
    {
        public Task<Guid?> AuthenticateAsync(string email, string password, CancellationToken cancellationToken) =>
            Task.FromResult<Guid?>(email == "owner@example.test" && password == "test-password" ? UserId : null);
    }

    private sealed class FakeAccessReader : IVendorAccessReader
    {
        public bool MembershipActive { get; set; } = true;
        public bool CanEdit { get; set; } = true;
        public bool CanPublish { get; set; } = true;

        public Task<bool> IsActiveUserAsync(Guid userId, CancellationToken cancellationToken) =>
            Task.FromResult(userId == UserId);

        public Task<IReadOnlyList<string>> GetActiveRolesAsync(Guid userId, CancellationToken cancellationToken) =>
            Task.FromResult<IReadOnlyList<string>>(userId == UserId ? ["customer"] : []);

        public Task<IReadOnlyList<VendorAccess>> GetActiveVendorsAsync(Guid userId, CancellationToken cancellationToken) =>
            Task.FromResult<IReadOnlyList<VendorAccess>>(userId == UserId
                ? [new VendorAccess(VendorId, "Test Vendor", "owner")] : []);

        public Task<bool> HasActiveMembershipAsync(Guid userId, Guid vendorId, CancellationToken cancellationToken) =>
            Task.FromResult(MembershipActive && userId == UserId && vendorId == VendorId);

        public Task<bool> CanManageCatalogAsync(Guid userId, Guid vendorId, CancellationToken cancellationToken) =>
            Task.FromResult(MembershipActive && CanEdit && userId == UserId && vendorId == VendorId);

        public Task<bool> CanPublishCatalogAsync(Guid userId, Guid vendorId, CancellationToken cancellationToken) =>
            Task.FromResult(MembershipActive && CanPublish && userId == UserId && vendorId == VendorId);
    }

    private sealed class FakeDraftProductWriter : IDraftProductWriter
    {
        public CreateDraftProduct? LastRequest { get; private set; }

        public Task<DraftProduct?> CreateAsync(Guid userId, Guid vendorId, CreateDraftProduct request,
            CancellationToken cancellationToken)
        {
            LastRequest = request;
            return Task.FromResult<DraftProduct?>(userId == UserId && vendorId == VendorId
                ? new DraftProduct(ProductId, request.Name, "draft") : null);
        }
    }

    private sealed class FakeProductVariantWriter : IProductVariantWriter
    {
        public CreateProductVariant? LastRequest { get; private set; }

        public Task<CreatedProductVariant?> CreateAsync(Guid userId, Guid vendorId, Guid productId,
            CreateProductVariant request, CancellationToken cancellationToken)
        {
            LastRequest = request;
            return Task.FromResult<CreatedProductVariant?>(
                userId == UserId && vendorId == VendorId && productId == ProductId
                    ? new CreatedProductVariant(Guid.NewGuid(), Guid.NewGuid()) : null);
        }
    }

    private sealed class FakeProductCategoryWriter : IProductCategoryWriter
    {
        public Task<bool> SetAsync(Guid userId, Guid vendorId, Guid productId, Guid categoryId,
            CancellationToken cancellationToken) => Task.FromResult(
                userId == UserId && vendorId == VendorId && productId == ProductId && categoryId != Guid.Empty);
    }

    private sealed class FakeProductPublisher : IProductPublisher
    {
        public Task<bool> PublishAsync(Guid userId, Guid vendorId, Guid productId,
            CancellationToken cancellationToken) => Task.FromResult(
                userId == UserId && vendorId == VendorId && productId == ProductId);
    }

    private sealed class FakeCatalogReader : IVendorCatalogReader
    {
        public Task<IReadOnlyList<CatalogCategory>> GetActiveCategoriesAsync(Guid userId, Guid vendorId,
            CancellationToken cancellationToken) => Task.FromResult<IReadOnlyList<CatalogCategory>>(
                userId == UserId && vendorId == VendorId
                    ? [new CatalogCategory(Guid.NewGuid(), "Ready-to-Wear", null)] : []);

        public Task<VendorCatalogPage> GetProductsAsync(Guid userId, Guid vendorId, Guid? after, int limit,
            CancellationToken cancellationToken) => Task.FromResult(
                new VendorCatalogPage(userId == UserId && vendorId == VendorId && after is null
                    ? [new PublicationFacts(ProductId, "Test Product", "draft", false, false, false, false)]
                    : [], null));

        public Task<VendorProductDetails?> GetProductDetailsAsync(Guid userId, Guid vendorId, Guid productId,
            CancellationToken cancellationToken) => Task.FromResult<VendorProductDetails?>(
                userId == UserId && vendorId == VendorId && productId == ProductId
                    ? new VendorProductDetails(ProductId, "Test Product", "Test description", "draft", [], false) : null);

        public Task<ProductPage> GetDraftProductsAsync(Guid userId, Guid vendorId, int limit,
            CancellationToken cancellationToken) => Task.FromResult(new ProductPage(0, []));

        public Task<ListingPage> GetListingsAsync(Guid userId, Guid vendorId, CatalogQuestion question,
            Guid? productId, int lowStockThreshold, int limit, CancellationToken cancellationToken) =>
            Task.FromResult(new ListingPage(0, []));

        public Task<PublicationFacts?> GetPublicationFactsAsync(Guid userId, Guid vendorId, Guid productId,
            CancellationToken cancellationToken) => Task.FromResult<PublicationFacts?>(null);
    }
}
