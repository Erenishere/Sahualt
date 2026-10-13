using System.Threading.RateLimiting;
using System.Security.Claims;
using Amazon.S3;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.DataProtection;
using Npgsql;
using SahulatAI.Application.Features.Assistant;
using SahulatAI.Application.Features.Admin;
using SahulatAI.Application.Features.Auth;
using SahulatAI.Application.Features.Catalog;
using SahulatAI.Application.Features.Marketplace;
using SahulatAI.Infrastructure.ML;
using SahulatAI.Infrastructure.Persistence;

var builder = WebApplication.CreateBuilder(args);
builder.Logging.ClearProviders();
builder.Logging.AddConsole();

builder.Services.AddControllers();
builder.Services.AddProblemDetails();

var connectionString = builder.Configuration.GetConnectionString("AssistantReader")
    ?? throw new InvalidOperationException("ConnectionStrings:AssistantReader is required.");
var identityConnectionString = builder.Configuration.GetConnectionString("IdentityReader")
    ?? throw new InvalidOperationException("ConnectionStrings:IdentityReader is required.");
var frontendOrigin = builder.Configuration["Frontend:Origin"]
    ?? throw new InvalidOperationException("Frontend:Origin is required.");

static NpgsqlDataSource CreateRuntimeDataSource(string value)
{
    var options = new NpgsqlConnectionStringBuilder(value) { CommandTimeout = 5, Timeout = 5 };
    if (string.IsNullOrWhiteSpace(options.Username) ||
        string.Equals(options.Username, "postgres", StringComparison.OrdinalIgnoreCase))
        throw new InvalidOperationException("Runtime database connections must use dedicated non-superuser logins.");
    return NpgsqlDataSource.Create(options.ConnectionString);
}

builder.Services.AddSingleton(CreateRuntimeDataSource(connectionString));
builder.Services.AddSingleton(new IdentityDataSource(CreateRuntimeDataSource(identityConnectionString)));
var registrationConnectionString = builder.Configuration.GetConnectionString("RegistrationWriter");
if (builder.Environment.IsDevelopment() && !string.IsNullOrWhiteSpace(registrationConnectionString))
{
    builder.Services.AddSingleton(new RegistrationDataSource(CreateRuntimeDataSource(registrationConnectionString)));
    builder.Services.AddScoped<IVendorRegistrationWriter, PostgresVendorRegistrationWriter>();
    builder.Services.AddScoped<ICustomerRegistrationWriter, PostgresCustomerRegistrationWriter>();
}
else
{
    builder.Services.AddScoped<IVendorRegistrationWriter, UnavailableVendorRegistrationWriter>();
    builder.Services.AddScoped<ICustomerRegistrationWriter, UnavailableCustomerRegistrationWriter>();
}
var catalogWriterConnectionString = builder.Configuration.GetConnectionString("CatalogWriter");
if (string.IsNullOrWhiteSpace(catalogWriterConnectionString))
{
    builder.Services.AddScoped<IDraftProductWriter, UnavailableDraftProductWriter>();
    builder.Services.AddScoped<IProductVariantWriter, UnavailableProductVariantWriter>();
    builder.Services.AddScoped<IProductCategoryWriter, UnavailableProductCategoryWriter>();
    builder.Services.AddScoped<IProductPublisher, UnavailableProductPublisher>();
    builder.Services.AddScoped<IListingStockWriter, UnavailableListingStockWriter>();
    builder.Services.AddScoped<IProductEditor, UnavailableProductEditor>();
}
else
{
    builder.Services.AddSingleton(new CatalogWriterDataSource(CreateRuntimeDataSource(catalogWriterConnectionString)));
    builder.Services.AddScoped<IDraftProductWriter, PostgresDraftProductWriter>();
    builder.Services.AddScoped<IProductVariantWriter, PostgresProductVariantWriter>();
    builder.Services.AddScoped<IProductCategoryWriter, PostgresProductCategoryWriter>();
    builder.Services.AddScoped<IProductPublisher, PostgresProductPublisher>();
    builder.Services.AddScoped<IListingStockWriter, PostgresListingStockWriter>();
    builder.Services.AddScoped<IProductEditor, PostgresProductEditor>();
}
var commerceConnectionString = builder.Configuration.GetConnectionString("CommerceWriter");
if (string.IsNullOrWhiteSpace(commerceConnectionString))
{
    builder.Services.AddScoped<IAccountStore, UnavailableAccountStore>();
    builder.Services.AddScoped<ICommerceStore, UnavailableCommerceStore>();
    builder.Services.AddScoped<IVendorSettingsStore, UnavailableVendorSettingsStore>();
}
else
{
    builder.Services.AddSingleton(new CommerceDataSource(CreateRuntimeDataSource(commerceConnectionString)));
    builder.Services.AddScoped<IAccountStore, PostgresAccountStore>();
    builder.Services.AddScoped<ICommerceStore, PostgresCommerceStore>();
    builder.Services.AddScoped<IVendorSettingsStore, PostgresVendorSettingsStore>();
}
var adminConnectionString = builder.Configuration.GetConnectionString("AdminWriter");
if (string.IsNullOrWhiteSpace(adminConnectionString))
    builder.Services.AddScoped<IAdminStore, UnavailableAdminStore>();
else
{
    builder.Services.AddSingleton(new AdminDataSource(CreateRuntimeDataSource(adminConnectionString)));
    builder.Services.AddScoped<IAdminStore, PostgresAdminStore>();
}
var mediaSection = builder.Configuration.GetSection("Media:S3");
var mediaValues = new[] { mediaSection["Endpoint"], mediaSection["Region"], mediaSection["Bucket"],
    mediaSection["AccessKey"], mediaSection["SecretKey"] };
var mediaProvider = builder.Configuration["Media:Provider"];
var hasImageStore = false;
if (mediaProvider == "Local")
{
    var rootPath = builder.Configuration["Media:Local:Root"];
    if (!builder.Environment.IsDevelopment() || string.IsNullOrWhiteSpace(rootPath) ||
        !Path.IsPathFullyQualified(rootPath) || mediaValues.Any(value => !string.IsNullOrWhiteSpace(value)))
        throw new InvalidOperationException("Local image storage requires a dedicated absolute path in development and no S3 configuration.");
    builder.Services.AddSingleton<IProductImageObjectStore>(new LocalProductImageStore(rootPath));
    hasImageStore = true;
}
else if (mediaProvider is null or "" or "S3")
{
    if (mediaProvider == "S3" || mediaValues.Any(value => !string.IsNullOrWhiteSpace(value)))
    {
        if (mediaValues.Any(string.IsNullOrWhiteSpace) ||
            !Uri.TryCreate(mediaSection["Endpoint"], UriKind.Absolute, out var mediaEndpoint) ||
            (mediaEndpoint.Scheme != Uri.UriSchemeHttps &&
             !(builder.Environment.IsDevelopment() && mediaEndpoint.Scheme == Uri.UriSchemeHttp &&
               mediaEndpoint.Host is "localhost" or "127.0.0.1" or "::1")))
            throw new InvalidOperationException("Media:S3 requires a bucket, region, credentials, and an HTTPS endpoint.");

        var mediaConfig = new AmazonS3Config
        {
            ServiceURL = mediaSection["Endpoint"],
            AuthenticationRegion = mediaSection["Region"],
            ForcePathStyle = true
        };
        builder.Services.AddSingleton<IAmazonS3>(new AmazonS3Client(
            mediaSection["AccessKey"], mediaSection["SecretKey"], mediaConfig));
        builder.Services.AddSingleton<IProductImageObjectStore>(provider => new S3ProductImageStore(
            provider.GetRequiredService<IAmazonS3>(), mediaSection["Bucket"]!));
        hasImageStore = true;
    }
}
else
{
    throw new InvalidOperationException("Media:Provider must be Local or S3.");
}
if (hasImageStore)
{
    builder.Services.AddScoped<IProductImageReader, PostgresProductImageReader>();
    if (string.IsNullOrWhiteSpace(catalogWriterConnectionString))
        builder.Services.AddScoped<IProductImageWriter, UnavailableProductImageStore>();
    else
        builder.Services.AddScoped<IProductImageWriter, PostgresProductImageWriter>();
}
else
{
    builder.Services.AddScoped<IProductImageWriter, UnavailableProductImageStore>();
    builder.Services.AddScoped<IProductImageReader, UnavailableProductImageStore>();
}
builder.Services.AddScoped<IVendorAccessReader, PostgresVendorAccessReader>();
builder.Services.AddScoped<IVendorCatalogReader, PostgresVendorCatalogReader>();
builder.Services.AddScoped<IPublicCatalogReader>(provider => new PostgresPublicCatalogReader(
    provider.GetRequiredService<NpgsqlDataSource>(),
    provider.GetService<IProductImageObjectStore>()));
builder.Services.Configure<CatalogSearchOptions>(builder.Configuration.GetSection(CatalogSearchOptions.SectionName));
builder.Services.AddScoped<ICatalogSearchService, PostgresCatalogSearchService>();
builder.Services.AddScoped<IUserAuthenticator, PostgresUserAuthenticator>();
builder.Services.AddScoped<VendorAssistantService>();
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.Configure<MlInferenceOptions>(builder.Configuration.GetSection(MlInferenceOptions.SectionName));
builder.Services.AddHttpClient<IMlInferenceClient, MlInferenceClient>(client =>
    client.Timeout = TimeSpan.FromMinutes(3))
    .ConfigurePrimaryHttpMessageHandler(() => new SocketsHttpHandler
    {
        AllowAutoRedirect = false,
        UseCookies = false,
        UseProxy = false
    });

var dataProtection = builder.Services.AddDataProtection().SetApplicationName("SahulatAI.Api");
if (builder.Environment.IsDevelopment())
{
    dataProtection.UseEphemeralDataProtectionProvider();
}
else
{
    var keysPath = builder.Configuration["DataProtection:KeysPath"]
        ?? throw new InvalidOperationException("DataProtection:KeysPath is required outside development.");
    dataProtection.PersistKeysToFileSystem(new DirectoryInfo(keysPath));
}

builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme)
    .AddCookie(options =>
    {
        options.Cookie.Name = builder.Environment.IsDevelopment() ? "sahulat_session" : "__Host-sahulat_session";
        options.Cookie.HttpOnly = true;
        options.Cookie.SameSite = SameSiteMode.Lax;
        options.Cookie.SecurePolicy = builder.Environment.IsDevelopment()
            ? CookieSecurePolicy.SameAsRequest : CookieSecurePolicy.Always;
        options.ExpireTimeSpan = TimeSpan.FromHours(8);
        options.SlidingExpiration = false;
        options.Events.OnRedirectToLogin = context =>
        {
            context.Response.StatusCode = StatusCodes.Status401Unauthorized;
            return Task.CompletedTask;
        };
        options.Events.OnRedirectToAccessDenied = context =>
        {
            context.Response.StatusCode = StatusCodes.Status403Forbidden;
            return Task.CompletedTask;
        };
    });
builder.Services.AddAuthorization();
builder.Services.AddCors(options => options.AddPolicy("frontend", policy =>
    policy.WithOrigins(frontendOrigin).AllowAnyHeader().AllowAnyMethod().AllowCredentials()));
builder.Services.AddRateLimiter(options =>
{
    options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
    options.AddPolicy("assistant", context => RateLimitPartition.GetFixedWindowLimiter(
        context.User.FindFirst(ClaimTypes.NameIdentifier)?.Value ?? context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions
        {
            PermitLimit = 30,
            Window = TimeSpan.FromMinutes(1),
            QueueLimit = 0
        }));
    options.AddPolicy("login", context => RateLimitPartition.GetFixedWindowLimiter(
        context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions
        {
            PermitLimit = 5,
            Window = TimeSpan.FromMinutes(1),
            QueueLimit = 0
        }));
    options.AddPolicy("registration", context => RateLimitPartition.GetFixedWindowLimiter(
        context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions
        {
            PermitLimit = 3,
            Window = TimeSpan.FromMinutes(1),
            QueueLimit = 0
        }));
    options.AddPolicy("catalog-write", context => RateLimitPartition.GetFixedWindowLimiter(
        context.User.FindFirst(ClaimTypes.NameIdentifier)?.Value ?? context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions
        {
            PermitLimit = 10,
            Window = TimeSpan.FromMinutes(1),
            QueueLimit = 0
        }));
    options.AddPolicy("public-read", context => RateLimitPartition.GetFixedWindowLimiter(
        context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions
        {
            PermitLimit = 120,
            Window = TimeSpan.FromMinutes(1),
            QueueLimit = 0
        }));
    options.AddPolicy("commerce-write", context => RateLimitPartition.GetFixedWindowLimiter(
        context.User.FindFirst(ClaimTypes.NameIdentifier)?.Value ?? context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions
        {
            PermitLimit = 20,
            Window = TimeSpan.FromMinutes(1),
            QueueLimit = 0
        }));
});

var app = builder.Build();

app.UseExceptionHandler();
if (!app.Environment.IsDevelopment()) app.UseHttpsRedirection();
app.UseCors("frontend");
app.Use(async (context, next) =>
{
    if (HttpMethods.IsPost(context.Request.Method) || HttpMethods.IsPut(context.Request.Method) ||
        HttpMethods.IsPatch(context.Request.Method) || HttpMethods.IsDelete(context.Request.Method))
    {
        var origin = context.Request.Headers.Origin.ToString();
        if (!string.Equals(origin, frontendOrigin, StringComparison.OrdinalIgnoreCase))
        {
            context.Response.StatusCode = StatusCodes.Status403Forbidden;
            return;
        }
    }
    await next(context);
});
app.UseAuthentication();
app.UseRateLimiter();
app.UseAuthorization();
app.MapGet("/health/live", () => Results.Ok(new { status = "live" })).AllowAnonymous();
app.MapGet("/health/ready", async (NpgsqlDataSource dataSource, CancellationToken cancellationToken) =>
{
    try
    {
        await using var command = dataSource.CreateCommand("SELECT 1");
        await command.ExecuteScalarAsync(cancellationToken);
        return (IResult)Results.Ok(new { status = "ready" });
    }
    catch (Exception) when (!cancellationToken.IsCancellationRequested)
    {
        return (IResult)Results.Json(new { status = "not_ready" }, statusCode: StatusCodes.Status503ServiceUnavailable);
    }
}).AllowAnonymous();
app.MapControllers();

app.Run();

public partial class Program { }
