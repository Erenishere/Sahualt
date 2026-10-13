using SahulatAI.Application.Features.Catalog;

namespace SahulatAI.Application.Features.Marketplace;

public sealed record PublicProductSummary(
    Guid ProductId,
    string Name,
    Guid VendorId,
    string VendorName,
    string VendorSlug,
    string? Category,
    decimal StartingPrice,
    string Currency,
    string Availability,
    int? AvailableStock,
    bool AllowsOffers,
    Guid? PrimaryImageId);

public sealed record PublicListing(
    Guid ListingId,
    Guid VariantId,
    string VariantCode,
    string? Sku,
    string? Color,
    string? Size,
    decimal Price,
    string Currency,
    string Availability,
    int? AvailableStock,
    bool AllowsOffers);

public sealed record PublicProductDetails(
    Guid ProductId,
    string Name,
    string Description,
    Guid VendorId,
    string VendorName,
    string VendorSlug,
    string? VendorDescription,
    string? Category,
    Guid? PrimaryImageId,
    IReadOnlyList<PublicListing> Listings);

public sealed record PublicProductPage(IReadOnlyList<PublicProductSummary> Items, Guid? NextAfter);

public interface IPublicCatalogReader
{
    Task<PublicProductPage> SearchAsync(string? query, string? category, string? vendorSlug,
        Guid? after, int limit, CancellationToken cancellationToken);
    Task<IReadOnlyList<PublicProductSummary>> ListSummariesByProductIdsAsync(
        IReadOnlyList<Guid> productIds, CancellationToken cancellationToken);
    Task<PublicProductDetails?> GetAsync(Guid productId, CancellationToken cancellationToken);
    Task<ProductImageContent?> GetImageAsync(Guid productId, Guid imageId,
        CancellationToken cancellationToken);
}

public sealed record AccountProfile(
    Guid UserId,
    string Email,
    string DisplayName,
    string? Phone,
    IReadOnlyList<CustomerAddress> Addresses);

public sealed record CustomerAddress(
    Guid AddressId,
    string Label,
    string RecipientName,
    string Phone,
    string AddressLine1,
    string? AddressLine2,
    string City,
    string? Province,
    string? PostalCode,
    bool IsDefault);

public sealed record UpdateAccountProfile(string DisplayName, string? Phone);
public sealed record SaveCustomerAddress(
    Guid? AddressId,
    string Label,
    string RecipientName,
    string Phone,
    string AddressLine1,
    string? AddressLine2,
    string City,
    string? Province,
    string? PostalCode,
    bool IsDefault);

public sealed record OfferRecord(
    Guid OfferId,
    string OfferNumber,
    Guid ListingId,
    Guid ProductId,
    string ProductName,
    Guid VendorId,
    string VendorName,
    decimal ListedPrice,
    decimal OfferedPrice,
    decimal? CounterPrice,
    string Currency,
    string Status,
    string? CustomerMessage,
    DateTimeOffset ExpiresAt,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt);

public sealed record CreateOffer(Guid ListingId, decimal OfferedPrice, string? Message);
public sealed record VendorOfferDecision(string Action, decimal? CounterPrice);

public sealed record CheckoutItem(Guid ListingId, int Quantity);
public sealed record DeliveryDetails(
    string Name,
    string Phone,
    string AddressLine1,
    string? AddressLine2,
    string City,
    string? Province,
    string? PostalCode);
public sealed record PlaceOrder(
    Guid IdempotencyKey,
    IReadOnlyList<CheckoutItem> Items,
    Guid? AcceptedOfferId,
    string PaymentMethod,
    DeliveryDetails Delivery);

public sealed record OrderItemRecord(
    Guid OrderItemId,
    Guid ListingId,
    Guid ProductId,
    Guid VariantId,
    string ItemName,
    string VariantCode,
    string? Sku,
    decimal UnitPrice,
    string Currency,
    int Quantity,
    decimal DiscountTotal,
    decimal LineTotal);

public sealed record OrderRecord(
    Guid OrderId,
    string OrderNumber,
    Guid CustomerUserId,
    Guid VendorId,
    string VendorName,
    string Status,
    string PaymentMethod,
    string PaymentStatus,
    string Currency,
    decimal Subtotal,
    decimal DiscountTotal,
    decimal DeliveryTotal,
    decimal Total,
    DeliveryDetails Delivery,
    DateTimeOffset PlacedAt,
    DateTimeOffset UpdatedAt,
    IReadOnlyList<OrderItemRecord> Items);

public enum CommerceWriteResult
{
    Updated,
    NotFound,
    Conflict,
    InsufficientStock,
    InvalidTransition
}

public interface IAccountStore
{
    Task<AccountProfile?> GetProfileAsync(Guid userId, CancellationToken cancellationToken);
    Task<CommerceWriteResult> UpdateProfileAsync(Guid userId, UpdateAccountProfile profile,
        CancellationToken cancellationToken);
    Task<CustomerAddress?> SaveAddressAsync(Guid userId, SaveCustomerAddress address,
        CancellationToken cancellationToken);
}

public interface ICommerceStore
{
    Task<IReadOnlyList<OfferRecord>> GetCustomerOffersAsync(Guid userId, string? status,
        int limit, CancellationToken cancellationToken);
    Task<OfferRecord?> GetCustomerOfferAsync(Guid userId, Guid offerId,
        CancellationToken cancellationToken);
    Task<OfferRecord?> CreateOfferAsync(Guid userId, CreateOffer request,
        CancellationToken cancellationToken);
    Task<CommerceWriteResult> WithdrawOfferAsync(Guid userId, Guid offerId,
        CancellationToken cancellationToken);
    Task<CommerceWriteResult> AcceptCounterOfferAsync(Guid userId, Guid offerId,
        CancellationToken cancellationToken);
    Task<IReadOnlyList<OfferRecord>> GetVendorOffersAsync(Guid userId, Guid vendorId,
        string? status, int limit, CancellationToken cancellationToken);
    Task<CommerceWriteResult> DecideOfferAsync(Guid userId, Guid vendorId, Guid offerId,
        VendorOfferDecision decision, CancellationToken cancellationToken);
    Task<OrderRecord?> PlaceOrderAsync(Guid userId, PlaceOrder request,
        CancellationToken cancellationToken);
    Task<IReadOnlyList<OrderRecord>> GetCustomerOrdersAsync(Guid userId, string? status,
        int limit, CancellationToken cancellationToken);
    Task<OrderRecord?> GetCustomerOrderAsync(Guid userId, Guid orderId,
        CancellationToken cancellationToken);
    Task<CommerceWriteResult> CancelCustomerOrderAsync(Guid userId, Guid orderId,
        CancellationToken cancellationToken);
    Task<IReadOnlyList<OrderRecord>> GetVendorOrdersAsync(Guid userId, Guid vendorId,
        string? status, int limit, CancellationToken cancellationToken);
    Task<CommerceWriteResult> TransitionVendorOrderAsync(Guid userId, Guid vendorId,
        Guid orderId, string nextStatus, CancellationToken cancellationToken);
    Task<VendorCommerceSummary?> GetVendorSummaryAsync(Guid userId, Guid vendorId,
        CancellationToken cancellationToken);
    Task<VendorAnalytics?> GetVendorAnalyticsAsync(Guid userId, Guid vendorId, int periodDays,
        CancellationToken cancellationToken);
}

public sealed record VendorCommerceSummary(
    int PendingOffers,
    int OpenOrders,
    int LowStockListings,
    int UnknownStockListings);

public sealed record VendorStoreProfile(
    Guid VendorId, string DisplayName, string Slug, string? Description, bool AllowCustomerOffers);

public sealed record UpdateVendorStoreProfile(
    string DisplayName, string? Description, bool AllowCustomerOffers);

public interface IVendorSettingsStore
{
    Task<VendorStoreProfile?> GetAsync(Guid userId, Guid vendorId, CancellationToken cancellationToken);
    Task<CommerceWriteResult> UpdateAsync(Guid userId, Guid vendorId, UpdateVendorStoreProfile profile,
        CancellationToken cancellationToken);
}

public sealed record CurrencyAmount(string Currency, decimal Amount);
public sealed record TopProductMetric(Guid ProductId, string Name, string Currency, int Quantity, decimal Revenue);
public sealed record VendorAnalytics(
    int PeriodDays,
    int OrdersPlaced,
    int OrdersCompleted,
    IReadOnlyList<CurrencyAmount> Revenue,
    IReadOnlyList<CurrencyAmount> AverageOrderValue,
    int OffersReceived,
    int OffersAccepted,
    int OffersConverted,
    IReadOnlyList<TopProductMetric> TopProducts);

public sealed class CommerceUnavailableException : Exception { }
public sealed class IdempotencyConflictException : Exception { }

public static class CommerceRules
{
    public static bool CanCustomerCancel(string currentStatus) => currentStatus is "placed" or "confirmed";

    public static bool CanVendorTransition(string currentStatus, string nextStatus) =>
        (currentStatus, nextStatus) is
            ("placed", "confirmed") or
            ("confirmed", "processing") or
            ("processing", "shipped") or
            ("shipped", "completed") or
            ("placed", "cancelled") or
            ("confirmed", "cancelled") or
            ("processing", "cancelled");

    public static decimal NegotiatedDiscount(decimal currentUnitPrice, decimal negotiatedUnitPrice, int quantity) =>
        Math.Max(0, currentUnitPrice - negotiatedUnitPrice) * quantity;
}
