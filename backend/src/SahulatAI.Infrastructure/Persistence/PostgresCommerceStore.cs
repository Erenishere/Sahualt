using System.Data;
using System.Security.Cryptography;
using System.Text.Json;
using Npgsql;
using NpgsqlTypes;
using SahulatAI.Application.Features.Marketplace;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresCommerceStore(CommerceDataSource commerce) : ICommerceStore
{
    private const string OfferProjection = """
        o.id, o.public_offer_number, o.listing_id, p.id, p.name, v.id, v.display_name,
        o.listed_price, o.offered_price, o.counter_price, o.currency, o.status,
        o.customer_message, o.expires_at, o.created_at, o.updated_at
        """;

    public Task<IReadOnlyList<OfferRecord>> GetCustomerOffersAsync(Guid userId, string? status,
        int limit, CancellationToken cancellationToken) => ReadOffersAsync(
            """
            WHERE o.customer_user_id = @user_id
              AND EXISTS (SELECT 1 FROM iam.users u WHERE u.id = @user_id AND u.status = 'active')
              AND (CAST(@status AS text) IS NULL OR o.status = @status)
            """, userId, null, status, limit, cancellationToken);

    public async Task<OfferRecord?> GetCustomerOfferAsync(Guid userId, Guid offerId,
        CancellationToken cancellationToken)
    {
        var offers = await ReadOffersAsync(
            """
            WHERE o.customer_user_id = @user_id AND o.id = @offer_id
              AND EXISTS (SELECT 1 FROM iam.users u WHERE u.id = @user_id AND u.status = 'active')
            """, userId, null, null, 1, cancellationToken, offerId);
        return offers.SingleOrDefault();
    }

    public async Task<OfferRecord?> CreateOfferAsync(Guid userId, CreateOffer request,
        CancellationToken cancellationToken)
    {
        await ExpireOffersAsync(userId, null, request.ListingId, cancellationToken);
        const string sql = """
            INSERT INTO commerce.offers (
                customer_user_id, vendor_id, listing_id, currency, listed_price,
                offered_price, customer_message, expires_at
            )
            SELECT @user_id, p.vendor_id, l.id, l.currency, l.price,
                   @offered_price, @message, now() + interval '7 days'
            FROM catalog.listings l
            JOIN catalog.product_variants pv ON pv.id = l.variant_id
            JOIN catalog.products p ON p.id = pv.product_id
            JOIN catalog.vendors v ON v.id = p.vendor_id
            JOIN inventory.inventory_balances b ON b.listing_id = l.id
            WHERE l.id = @listing_id AND l.status = 'active' AND l.availability = 'in_stock'
              AND l.price IS NOT NULL AND @offered_price > 0 AND @offered_price < l.price
              AND l.allow_customer_offers AND v.allow_customer_offers
              AND pv.status = 'active' AND p.status = 'published' AND v.status = 'active'
              AND b.on_hand_quantity IS NOT NULL AND b.on_hand_quantity > b.reserved_quantity
              AND EXISTS (
                  SELECT 1 FROM iam.users u JOIN iam.user_roles r ON r.user_id = u.id
                  WHERE u.id = @user_id AND u.status = 'active'
                    AND r.role = 'customer' AND r.status = 'active'
              )
            RETURNING id
            """;
        await using var command = commerce.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("listing_id", request.ListingId);
        command.Parameters.AddWithValue("offered_price", request.OfferedPrice);
        command.Parameters.Add("message", NpgsqlDbType.Text).Value = (object?)request.Message ?? DBNull.Value;
        Guid? offerId;
        try { offerId = await command.ExecuteScalarAsync(cancellationToken) as Guid?; }
        catch (PostgresException error) when (error.SqlState == PostgresErrorCodes.UniqueViolation)
        {
            return null;
        }
        return offerId is Guid id ? await GetCustomerOfferAsync(userId, id, cancellationToken) : null;
    }

    public async Task<CommerceWriteResult> WithdrawOfferAsync(Guid userId, Guid offerId,
        CancellationToken cancellationToken)
    {
        await ExpireOffersAsync(userId, null, null, cancellationToken);
        const string sql = """
            UPDATE commerce.offers o SET status = 'withdrawn', updated_at = now()
            WHERE o.id = @offer_id AND o.customer_user_id = @user_id
              AND o.status IN ('pending', 'countered')
              AND EXISTS (SELECT 1 FROM iam.users u WHERE u.id = @user_id AND u.status = 'active')
            RETURNING o.id
            """;
        await using var command = commerce.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("offer_id", offerId);
        if (await command.ExecuteScalarAsync(cancellationToken) is Guid) return CommerceWriteResult.Updated;
        return await CustomerOfferExistsAsync(userId, offerId, cancellationToken)
            ? CommerceWriteResult.InvalidTransition : CommerceWriteResult.NotFound;
    }

    public async Task<CommerceWriteResult> AcceptCounterOfferAsync(Guid userId, Guid offerId,
        CancellationToken cancellationToken)
    {
        await ExpireOffersAsync(userId, null, null, cancellationToken);
        const string sql = """
            UPDATE commerce.offers o SET status = 'accepted', accepted_at = now(), updated_at = now()
            WHERE o.id = @offer_id AND o.customer_user_id = @user_id
              AND o.status = 'countered' AND o.counter_price IS NOT NULL AND o.expires_at > now()
              AND EXISTS (SELECT 1 FROM iam.users u JOIN iam.user_roles r ON r.user_id = u.id
                          WHERE u.id = @user_id AND u.status = 'active'
                            AND r.role = 'customer' AND r.status = 'active')
            RETURNING o.id
            """;
        await using var command = commerce.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("offer_id", offerId);
        if (await command.ExecuteScalarAsync(cancellationToken) is Guid) return CommerceWriteResult.Updated;
        return await CustomerOfferExistsAsync(userId, offerId, cancellationToken)
            ? CommerceWriteResult.InvalidTransition : CommerceWriteResult.NotFound;
    }

    public Task<IReadOnlyList<OfferRecord>> GetVendorOffersAsync(Guid userId, Guid vendorId,
        string? status, int limit, CancellationToken cancellationToken) => ReadOffersAsync(
            """
            WHERE o.vendor_id = @vendor_id
              AND EXISTS (
                  SELECT 1 FROM iam.users u
                  JOIN iam.vendor_memberships m ON m.user_id = u.id
                  JOIN catalog.vendors av ON av.id = m.vendor_id
                  WHERE u.id = @user_id AND u.status = 'active' AND m.vendor_id = @vendor_id
                    AND m.status = 'active' AND av.status = 'active'
              )
              AND (CAST(@status AS text) IS NULL OR o.status = @status)
            """, userId, vendorId, status, limit, cancellationToken);

    public async Task<CommerceWriteResult> DecideOfferAsync(Guid userId, Guid vendorId,
        Guid offerId, VendorOfferDecision decision, CancellationToken cancellationToken)
    {
        await ExpireOffersAsync(null, vendorId, null, cancellationToken);
        var (status, setCounter, accepted) = decision.Action switch
        {
            "accept" => ("accepted", false, true),
            "counter" => ("countered", true, false),
            "reject" => ("rejected", false, false),
            _ => ("", false, false)
        };
        if (status.Length == 0) return CommerceWriteResult.InvalidTransition;
        const string sql = """
            UPDATE commerce.offers o SET
                status = @status,
                counter_price = CASE WHEN @set_counter THEN @counter_price ELSE counter_price END,
                accepted_at = CASE WHEN @accepted THEN now() ELSE accepted_at END,
                updated_at = now()
            WHERE o.id = @offer_id AND o.vendor_id = @vendor_id
              AND ((@status IN ('accepted', 'countered') AND o.status = 'pending')
                   OR (@status = 'rejected' AND o.status IN ('pending', 'countered')))
              AND o.expires_at > now()
              AND (NOT @set_counter OR (@counter_price > o.offered_price AND @counter_price <= o.listed_price))
              AND EXISTS (
                  SELECT 1 FROM iam.users u
                  JOIN iam.vendor_memberships m ON m.user_id = u.id
                  JOIN catalog.vendors v ON v.id = m.vendor_id
                  WHERE u.id = @user_id AND u.status = 'active' AND m.vendor_id = @vendor_id
                    AND m.status = 'active' AND m.role IN ('owner', 'manager', 'staff')
                    AND v.status = 'active'
              )
            RETURNING o.id
            """;
        await using var command = commerce.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("offer_id", offerId);
        command.Parameters.AddWithValue("status", status);
        command.Parameters.AddWithValue("set_counter", setCounter);
        command.Parameters.AddWithValue("accepted", accepted);
        command.Parameters.Add("counter_price", NpgsqlDbType.Numeric).Value =
            (object?)decision.CounterPrice ?? DBNull.Value;
        if (await command.ExecuteScalarAsync(cancellationToken) is Guid) return CommerceWriteResult.Updated;
        return CommerceWriteResult.InvalidTransition;
    }

    public async Task<OrderRecord?> PlaceOrderAsync(Guid userId, PlaceOrder request,
        CancellationToken cancellationToken)
    {
        await using var connection = await commerce.DataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, cancellationToken);

        const string idempotencyLockSql = "SELECT pg_advisory_xact_lock(hashtextextended(@lock_key, 0))";
        await using (var idempotencyLock = new NpgsqlCommand(idempotencyLockSql, connection, transaction))
        {
            idempotencyLock.Parameters.AddWithValue("lock_key", $"{userId:D}:{request.IdempotencyKey:D}");
            await idempotencyLock.ExecuteNonQueryAsync(cancellationToken);
        }

        var fingerprint = Fingerprint(request);
        const string existingSql = """
            SELECT o.id, o.idempotency_fingerprint FROM commerce.orders o
            WHERE o.customer_user_id = @user_id AND o.idempotency_key = @idempotency_key
              AND EXISTS (SELECT 1 FROM iam.users u JOIN iam.user_roles r ON r.user_id = u.id
                          WHERE u.id = @user_id AND u.status = 'active'
                            AND r.role = 'customer' AND r.status = 'active')
            """;
        await using (var existingCommand = new NpgsqlCommand(existingSql, connection, transaction))
        {
            existingCommand.Parameters.AddWithValue("user_id", userId);
            existingCommand.Parameters.AddWithValue("idempotency_key", request.IdempotencyKey);
            await using var existingReader = await existingCommand.ExecuteReaderAsync(cancellationToken);
            if (await existingReader.ReadAsync(cancellationToken))
            {
                var existingId = existingReader.GetGuid(0);
                var existingFingerprint = existingReader.GetString(1);
                await existingReader.DisposeAsync();
                if (!CryptographicOperations.FixedTimeEquals(
                        Convert.FromHexString(existingFingerprint), Convert.FromHexString(fingerprint)))
                    throw new IdempotencyConflictException();
                var existing = await ReadOrderAsync(connection, transaction, "o.id = @order_id",
                    userId, null, existingId, null, cancellationToken);
                await transaction.CommitAsync(cancellationToken);
                return existing;
            }
        }

        var quantities = request.Items.ToDictionary(item => item.ListingId, item => item.Quantity);
        var listingIds = quantities.Keys.ToArray();
        const string listingsSql = """
            SELECT l.id, pv.id, p.id, p.name, pv.variant_code, pv.sku,
                   p.vendor_id, l.price, l.currency, b.on_hand_quantity, b.reserved_quantity
            FROM catalog.listings l
            JOIN catalog.product_variants pv ON pv.id = l.variant_id
            JOIN catalog.products p ON p.id = pv.product_id
            JOIN catalog.vendors v ON v.id = p.vendor_id
            JOIN inventory.inventory_balances b ON b.listing_id = l.id
            WHERE l.id = ANY(@listing_ids) AND l.status = 'active' AND l.availability = 'in_stock'
              AND pv.status = 'active' AND p.status = 'published' AND v.status = 'active'
              AND l.price IS NOT NULL AND l.currency IS NOT NULL AND b.on_hand_quantity IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM iam.users u JOIN iam.user_roles r ON r.user_id = u.id
                  WHERE u.id = @user_id AND u.status = 'active'
                    AND r.role = 'customer' AND r.status = 'active'
              )
            ORDER BY l.id
            FOR UPDATE OF l, b
            """;
        await using var listingsCommand = new NpgsqlCommand(listingsSql, connection, transaction);
        listingsCommand.Parameters.AddWithValue("listing_ids", listingIds);
        listingsCommand.Parameters.AddWithValue("user_id", userId);
        var lines = new List<OrderLine>();
        await using (var reader = await listingsCommand.ExecuteReaderAsync(cancellationToken))
        {
            while (await reader.ReadAsync(cancellationToken))
                lines.Add(new OrderLine(reader.GetGuid(0), reader.GetGuid(1), reader.GetGuid(2),
                    reader.GetString(3), reader.GetString(4), reader.IsDBNull(5) ? null : reader.GetString(5),
                    reader.GetGuid(6), reader.GetDecimal(7), reader.GetString(8),
                    reader.GetInt32(9), reader.GetInt32(10), quantities[reader.GetGuid(0)]));
        }
        if (lines.Count != listingIds.Length || lines.Select(x => x.VendorId).Distinct().Count() != 1 ||
            lines.Select(x => x.Currency).Distinct(StringComparer.Ordinal).Count() != 1 ||
            lines.Any(x => x.OnHand - x.Reserved < x.Quantity))
        {
            await transaction.RollbackAsync(cancellationToken);
            return null;
        }

        decimal discount = 0;
        Guid? discountedListingId = null;
        if (request.AcceptedOfferId is Guid acceptedOfferId)
        {
            const string offerSql = """
                SELECT listing_id, listed_price, COALESCE(counter_price, offered_price)
                FROM commerce.offers
                WHERE id = @offer_id AND customer_user_id = @user_id AND status = 'accepted'
                  AND expires_at > now() FOR UPDATE
                """;
            await using var offer = new NpgsqlCommand(offerSql, connection, transaction);
            offer.Parameters.AddWithValue("offer_id", acceptedOfferId);
            offer.Parameters.AddWithValue("user_id", userId);
            await using var reader = await offer.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken) || !quantities.ContainsKey(reader.GetGuid(0)))
            {
                await transaction.RollbackAsync(cancellationToken);
                return null;
            }
            discountedListingId = reader.GetGuid(0);
            var negotiatedPrice = reader.GetDecimal(2);
            var currentPrice = lines.Single(line => line.ListingId == discountedListingId.Value).Price;
            discount = CommerceRules.NegotiatedDiscount(
                currentPrice, negotiatedPrice, quantities[discountedListingId.Value]);
        }

        var subtotal = lines.Sum(x => x.Price * x.Quantity);
        var vendorId = lines[0].VendorId;
        var currency = lines[0].Currency;
        const string orderSql = """
            INSERT INTO commerce.orders (
                customer_user_id, vendor_id, accepted_offer_id, idempotency_key, idempotency_fingerprint, status,
                payment_method, payment_status, currency, subtotal, discount_total,
                delivery_total, total, delivery_name, delivery_phone, delivery_address_line1,
                delivery_address_line2, delivery_city, delivery_province, delivery_postal_code
            ) VALUES (
                @user_id, @vendor_id, @offer_id, @idempotency_key, @idempotency_fingerprint, 'placed',
                'cash_on_delivery', 'cod_due', @currency, @subtotal, @discount,
                0, @total, @name, @phone, @line1, @line2, @city, @province, @postal_code
            ) RETURNING id
            """;
        await using var order = new NpgsqlCommand(orderSql, connection, transaction);
        order.Parameters.AddWithValue("user_id", userId);
        order.Parameters.AddWithValue("vendor_id", vendorId);
        order.Parameters.Add("offer_id", NpgsqlDbType.Uuid).Value = (object?)request.AcceptedOfferId ?? DBNull.Value;
        order.Parameters.AddWithValue("idempotency_key", request.IdempotencyKey);
        order.Parameters.AddWithValue("idempotency_fingerprint", fingerprint);
        order.Parameters.AddWithValue("currency", currency);
        order.Parameters.AddWithValue("subtotal", subtotal);
        order.Parameters.AddWithValue("discount", discount);
        order.Parameters.AddWithValue("total", subtotal - discount);
        AddDelivery(order, request.Delivery);
        var orderId = (Guid)(await order.ExecuteScalarAsync(cancellationToken)
            ?? throw new InvalidOperationException("Order insert did not return an identifier."));

        foreach (var line in lines)
        {
            var lineDiscount = line.ListingId == discountedListingId ? discount : 0;

            const string itemSql = """
                INSERT INTO commerce.order_items (
                    order_id, listing_id, product_id, variant_id, item_name, variant_code,
                    sku, unit_price, currency, quantity, discount_total, line_total
                ) VALUES (
                    @order_id, @listing_id, @product_id, @variant_id, @item_name, @variant_code,
                    @sku, @price, @currency, @quantity, @discount, @line_total
                ) RETURNING id
                """;
            await using var item = new NpgsqlCommand(itemSql, connection, transaction);
            item.Parameters.AddWithValue("order_id", orderId);
            item.Parameters.AddWithValue("listing_id", line.ListingId);
            item.Parameters.AddWithValue("product_id", line.ProductId);
            item.Parameters.AddWithValue("variant_id", line.VariantId);
            item.Parameters.AddWithValue("item_name", line.Name);
            item.Parameters.AddWithValue("variant_code", line.VariantCode);
            item.Parameters.Add("sku", NpgsqlDbType.Text).Value = (object?)line.Sku ?? DBNull.Value;
            item.Parameters.AddWithValue("price", line.Price);
            item.Parameters.AddWithValue("currency", line.Currency);
            item.Parameters.AddWithValue("quantity", line.Quantity);
            item.Parameters.AddWithValue("discount", lineDiscount);
            item.Parameters.AddWithValue("line_total", line.Price * line.Quantity - lineDiscount);
            var orderItemId = (Guid)(await item.ExecuteScalarAsync(cancellationToken))!;

            const string reserveSql = """
                UPDATE inventory.inventory_balances SET
                    reserved_quantity = reserved_quantity + @quantity, updated_at = now()
                WHERE listing_id = @listing_id;
                INSERT INTO inventory.inventory_reservations (order_item_id, listing_id, quantity)
                VALUES (@order_item_id, @listing_id, @quantity);
                """;
            await using var reserve = new NpgsqlCommand(reserveSql, connection, transaction);
            reserve.Parameters.AddWithValue("quantity", line.Quantity);
            reserve.Parameters.AddWithValue("listing_id", line.ListingId);
            reserve.Parameters.AddWithValue("order_item_id", orderItemId);
            await reserve.ExecuteNonQueryAsync(cancellationToken);
        }

        if (request.AcceptedOfferId is Guid convertedOfferId)
        {
            const string convertSql = """
                UPDATE commerce.offers SET status = 'converted', updated_at = now()
                WHERE id = @offer_id AND status = 'accepted'
                """;
            await using var convert = new NpgsqlCommand(convertSql, connection, transaction);
            convert.Parameters.AddWithValue("offer_id", convertedOfferId);
            await convert.ExecuteNonQueryAsync(cancellationToken);
        }
        await WriteEventAsync(connection, transaction, userId, vendorId, orderId,
            "order", "order.placed", cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return await GetCustomerOrderAsync(userId, orderId, cancellationToken);
    }

    public async Task<IReadOnlyList<OrderRecord>> GetCustomerOrdersAsync(Guid userId, string? status,
        int limit, CancellationToken cancellationToken)
    {
        return await ReadOrderListAsync(
            """
            o.customer_user_id = @user_id AND (CAST(@status AS text) IS NULL OR o.status = @status)
            AND EXISTS (SELECT 1 FROM iam.users u JOIN iam.user_roles r ON r.user_id = u.id
                        WHERE u.id = @user_id AND u.status = 'active'
                          AND r.role = 'customer' AND r.status = 'active')
            """,
            userId, null, status, limit, cancellationToken);
    }

    public Task<OrderRecord?> GetCustomerOrderAsync(Guid userId, Guid orderId,
        CancellationToken cancellationToken) => ReadSingleOrderAsync(
            """
            o.customer_user_id = @user_id AND o.id = @order_id
            AND EXISTS (SELECT 1 FROM iam.users u JOIN iam.user_roles r ON r.user_id = u.id
                        WHERE u.id = @user_id AND u.status = 'active'
                          AND r.role = 'customer' AND r.status = 'active')
            """, userId, null, orderId, cancellationToken);

    public async Task<CommerceWriteResult> CancelCustomerOrderAsync(Guid userId, Guid orderId,
        CancellationToken cancellationToken) => await ChangeOrderStatusAsync(
            userId, null, orderId, "cancelled", true, cancellationToken);

    public Task<IReadOnlyList<OrderRecord>> GetVendorOrdersAsync(Guid userId, Guid vendorId,
        string? status, int limit, CancellationToken cancellationToken) => ReadOrderListAsync(
            """
            o.vendor_id = @vendor_id AND (CAST(@status AS text) IS NULL OR o.status = @status)
            AND EXISTS (
                SELECT 1 FROM iam.users u JOIN iam.vendor_memberships m ON m.user_id = u.id
                JOIN catalog.vendors v ON v.id = m.vendor_id
                WHERE u.id = @user_id AND u.status = 'active' AND m.vendor_id = @vendor_id
                  AND m.status = 'active' AND m.role IN ('owner', 'manager', 'staff')
                  AND v.status = 'active'
            )
            """, userId, vendorId, status, limit, cancellationToken);

    public async Task<CommerceWriteResult> TransitionVendorOrderAsync(Guid userId, Guid vendorId,
        Guid orderId, string nextStatus, CancellationToken cancellationToken) =>
        await ChangeOrderStatusAsync(userId, vendorId, orderId, nextStatus, false, cancellationToken);

    public async Task<VendorCommerceSummary?> GetVendorSummaryAsync(Guid userId, Guid vendorId,
        CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT
              (SELECT count(*)::int FROM commerce.offers WHERE vendor_id = @vendor_id AND status IN ('pending','countered')),
              (SELECT count(*)::int FROM commerce.orders WHERE vendor_id = @vendor_id AND status NOT IN ('completed','cancelled')),
              (SELECT count(*)::int FROM catalog.listings l
               JOIN catalog.product_variants pv ON pv.id = l.variant_id
               JOIN catalog.products p ON p.id = pv.product_id
               JOIN inventory.inventory_balances b ON b.listing_id = l.id
               WHERE p.vendor_id = @vendor_id AND l.status = 'active' AND b.on_hand_quantity IS NOT NULL
                 AND b.on_hand_quantity - b.reserved_quantity BETWEEN 0 AND 5),
              (SELECT count(*)::int FROM catalog.listings l
               JOIN catalog.product_variants pv ON pv.id = l.variant_id
               JOIN catalog.products p ON p.id = pv.product_id
               LEFT JOIN inventory.inventory_balances b ON b.listing_id = l.id
               WHERE p.vendor_id = @vendor_id AND l.status = 'active' AND b.on_hand_quantity IS NULL)
            WHERE EXISTS (
                SELECT 1 FROM iam.users u JOIN iam.vendor_memberships m ON m.user_id = u.id
                JOIN catalog.vendors v ON v.id = m.vendor_id
                WHERE u.id = @user_id AND u.status = 'active' AND m.vendor_id = @vendor_id
                  AND m.status = 'active' AND v.status = 'active'
            )
            """;
        await using var command = commerce.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken)
            ? new VendorCommerceSummary(reader.GetInt32(0), reader.GetInt32(1), reader.GetInt32(2), reader.GetInt32(3))
            : null;
    }

    public async Task<VendorAnalytics?> GetVendorAnalyticsAsync(Guid userId, Guid vendorId,
        int periodDays, CancellationToken cancellationToken)
    {
        await using var connection = await commerce.DataSource.OpenConnectionAsync(cancellationToken);
        const string authorizationSql = """
            SELECT EXISTS (
                SELECT 1 FROM iam.users u JOIN iam.vendor_memberships m ON m.user_id = u.id
                JOIN catalog.vendors v ON v.id = m.vendor_id
                WHERE u.id = @user_id AND u.status = 'active' AND m.vendor_id = @vendor_id
                  AND m.status = 'active' AND m.role IN ('owner', 'manager') AND v.status = 'active'
            )
            """;
        await using (var authorization = new NpgsqlCommand(authorizationSql, connection))
        {
            authorization.Parameters.AddWithValue("user_id", userId);
            authorization.Parameters.AddWithValue("vendor_id", vendorId);
            if (await authorization.ExecuteScalarAsync(cancellationToken) is not true) return null;
        }

        const string countsSql = """
            SELECT count(*)::int,
                   count(*) FILTER (WHERE status = 'completed' AND payment_status = 'paid')::int
            FROM commerce.orders
            WHERE vendor_id = @vendor_id
              AND placed_at >= now() - make_interval(days => @period_days)
            """;
        int ordersPlaced;
        int ordersCompleted;
        await using (var counts = new NpgsqlCommand(countsSql, connection))
        {
            AddAnalyticsParameters(counts, vendorId, periodDays);
            await using var reader = await counts.ExecuteReaderAsync(cancellationToken);
            await reader.ReadAsync(cancellationToken);
            ordersPlaced = reader.GetInt32(0);
            ordersCompleted = reader.GetInt32(1);
        }

        const string moneySql = """
            SELECT currency, sum(total), avg(total)
            FROM commerce.orders
            WHERE vendor_id = @vendor_id AND status = 'completed' AND payment_status = 'paid'
              AND placed_at >= now() - make_interval(days => @period_days)
            GROUP BY currency ORDER BY currency
            """;
        var revenue = new List<CurrencyAmount>();
        var average = new List<CurrencyAmount>();
        await using (var money = new NpgsqlCommand(moneySql, connection))
        {
            AddAnalyticsParameters(money, vendorId, periodDays);
            await using var reader = await money.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                revenue.Add(new CurrencyAmount(reader.GetString(0), reader.GetDecimal(1)));
                average.Add(new CurrencyAmount(reader.GetString(0), decimal.Round(reader.GetDecimal(2), 2)));
            }
        }

        const string offersSql = """
            SELECT count(*)::int,
                   count(*) FILTER (WHERE status IN ('accepted', 'converted'))::int,
                   count(*) FILTER (WHERE status = 'converted')::int
            FROM commerce.offers
            WHERE vendor_id = @vendor_id
              AND created_at >= now() - make_interval(days => @period_days)
            """;
        int offersReceived;
        int offersAccepted;
        int offersConverted;
        await using (var offers = new NpgsqlCommand(offersSql, connection))
        {
            AddAnalyticsParameters(offers, vendorId, periodDays);
            await using var reader = await offers.ExecuteReaderAsync(cancellationToken);
            await reader.ReadAsync(cancellationToken);
            offersReceived = reader.GetInt32(0);
            offersAccepted = reader.GetInt32(1);
            offersConverted = reader.GetInt32(2);
        }

        const string productsSql = """
            SELECT oi.product_id, oi.item_name, oi.currency, sum(oi.quantity)::int, sum(oi.line_total)
            FROM commerce.order_items oi JOIN commerce.orders o ON o.id = oi.order_id
            WHERE o.vendor_id = @vendor_id AND o.status = 'completed' AND o.payment_status = 'paid'
              AND o.placed_at >= now() - make_interval(days => @period_days)
            GROUP BY oi.product_id, oi.item_name, oi.currency
            ORDER BY sum(oi.quantity) DESC, sum(oi.line_total) DESC, oi.product_id
            LIMIT 10
            """;
        var products = new List<TopProductMetric>();
        await using (var command = new NpgsqlCommand(productsSql, connection))
        {
            AddAnalyticsParameters(command, vendorId, periodDays);
            await using var reader = await command.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
                products.Add(new TopProductMetric(reader.GetGuid(0), reader.GetString(1), reader.GetString(2),
                    reader.GetInt32(3), reader.GetDecimal(4)));
        }
        return new VendorAnalytics(periodDays, ordersPlaced, ordersCompleted, revenue, average,
            offersReceived, offersAccepted, offersConverted, products);
    }

    private async Task<IReadOnlyList<OfferRecord>> ReadOffersAsync(string where, Guid userId,
        Guid? vendorId, string? status, int limit, CancellationToken cancellationToken, Guid? offerId = null)
    {
        await ExpireOffersAsync(vendorId is null ? userId : null, vendorId, null, cancellationToken);
        var sql = $"""
            SELECT {OfferProjection}
            FROM commerce.offers o
            JOIN catalog.listings l ON l.id = o.listing_id
            JOIN catalog.product_variants pv ON pv.id = l.variant_id
            JOIN catalog.products p ON p.id = pv.product_id
            JOIN catalog.vendors v ON v.id = o.vendor_id
            {where}
            ORDER BY o.created_at DESC, o.id DESC LIMIT @limit
            """;
        await using var command = commerce.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        if (vendorId is Guid vendor) command.Parameters.AddWithValue("vendor_id", vendor);
        if (offerId is Guid offer) command.Parameters.AddWithValue("offer_id", offer);
        command.Parameters.Add("status", NpgsqlDbType.Text).Value = (object?)status ?? DBNull.Value;
        command.Parameters.AddWithValue("limit", limit);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<OfferRecord>();
        while (await reader.ReadAsync(cancellationToken)) result.Add(ReadOffer(reader));
        return result;
    }

    private static OfferRecord ReadOffer(NpgsqlDataReader r) => new(
        r.GetGuid(0), r.GetString(1), r.GetGuid(2), r.GetGuid(3), r.GetString(4),
        r.GetGuid(5), r.GetString(6), r.GetDecimal(7), r.GetDecimal(8),
        r.IsDBNull(9) ? null : r.GetDecimal(9), r.GetString(10), r.GetString(11),
        r.IsDBNull(12) ? null : r.GetString(12), r.GetFieldValue<DateTimeOffset>(13),
        r.GetFieldValue<DateTimeOffset>(14), r.GetFieldValue<DateTimeOffset>(15));

    private async Task<bool> CustomerOfferExistsAsync(Guid userId, Guid offerId, CancellationToken cancellationToken)
    {
        const string sql = "SELECT EXISTS (SELECT 1 FROM commerce.offers WHERE id=@offer_id AND customer_user_id=@user_id)";
        await using var command = commerce.DataSource.CreateCommand(sql);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("offer_id", offerId);
        return await command.ExecuteScalarAsync(cancellationToken) is true;
    }

    private async Task ExpireOffersAsync(Guid? customerId, Guid? vendorId, Guid? listingId,
        CancellationToken cancellationToken)
    {
        const string sql = """
            UPDATE commerce.offers SET status = 'expired', updated_at = now()
            WHERE status IN ('pending', 'countered') AND expires_at <= now()
              AND (CAST(@customer_id AS uuid) IS NULL OR customer_user_id = @customer_id)
              AND (CAST(@vendor_id AS uuid) IS NULL OR vendor_id = @vendor_id)
              AND (CAST(@listing_id AS uuid) IS NULL OR listing_id = @listing_id)
            """;
        await using var command = commerce.DataSource.CreateCommand(sql);
        command.Parameters.Add("customer_id", NpgsqlDbType.Uuid).Value = (object?)customerId ?? DBNull.Value;
        command.Parameters.Add("vendor_id", NpgsqlDbType.Uuid).Value = (object?)vendorId ?? DBNull.Value;
        command.Parameters.Add("listing_id", NpgsqlDbType.Uuid).Value = (object?)listingId ?? DBNull.Value;
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private async Task<IReadOnlyList<OrderRecord>> ReadOrderListAsync(string where, Guid userId,
        Guid? vendorId, string? status, int limit, CancellationToken cancellationToken)
    {
        var sql = $"SELECT o.id FROM commerce.orders o WHERE {where} ORDER BY o.placed_at DESC, o.id DESC LIMIT @limit";
        await using var connection = await commerce.DataSource.OpenConnectionAsync(cancellationToken);
        var ids = new List<Guid>();
        await using (var command = new NpgsqlCommand(sql, connection))
        {
            command.Parameters.AddWithValue("user_id", userId);
            if (vendorId is Guid vendor) command.Parameters.AddWithValue("vendor_id", vendor);
            command.Parameters.Add("status", NpgsqlDbType.Text).Value = (object?)status ?? DBNull.Value;
            command.Parameters.AddWithValue("limit", limit);
            await using var reader = await command.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken)) ids.Add(reader.GetGuid(0));
        }
        var orders = new List<OrderRecord>();
        foreach (var id in ids)
        {
            var order = await ReadOrderAsync(connection, null, "o.id = @order_id", userId, vendorId,
                id, null, cancellationToken);
            if (order is not null) orders.Add(order);
        }
        return orders;
    }

    private async Task<OrderRecord?> ReadSingleOrderAsync(string where, Guid userId, Guid? vendorId,
        Guid orderId, CancellationToken cancellationToken)
    {
        await using var connection = await commerce.DataSource.OpenConnectionAsync(cancellationToken);
        return await ReadOrderAsync(connection, null, where, userId, vendorId, orderId, null, cancellationToken);
    }

    private static async Task<OrderRecord?> ReadOrderAsync(NpgsqlConnection connection,
        NpgsqlTransaction? transaction, string where, Guid userId, Guid? vendorId, Guid? orderId,
        Guid? idempotencyKey, CancellationToken cancellationToken)
    {
        var sql = $"""
            SELECT o.id, o.public_order_number, o.customer_user_id, o.vendor_id, v.display_name,
                   o.status, o.payment_method, o.payment_status, o.currency, o.subtotal,
                   o.discount_total, o.delivery_total, o.total, o.delivery_name, o.delivery_phone,
                   o.delivery_address_line1, o.delivery_address_line2, o.delivery_city,
                   o.delivery_province, o.delivery_postal_code, o.placed_at, o.updated_at
            FROM commerce.orders o JOIN catalog.vendors v ON v.id = o.vendor_id
            WHERE {where}
            """;
        await using var command = new NpgsqlCommand(sql, connection, transaction);
        command.Parameters.AddWithValue("user_id", userId);
        if (vendorId is Guid vendor) command.Parameters.AddWithValue("vendor_id", vendor);
        if (orderId is Guid id) command.Parameters.AddWithValue("order_id", id);
        if (idempotencyKey is Guid key) command.Parameters.AddWithValue("idempotency_key", key);
        OrderHeader header;
        await using (var reader = await command.ExecuteReaderAsync(cancellationToken))
        {
            if (!await reader.ReadAsync(cancellationToken)) return null;
            header = new OrderHeader(
                reader.GetGuid(0), reader.GetString(1), reader.GetGuid(2), reader.GetGuid(3), reader.GetString(4),
                reader.GetString(5), reader.GetString(6), reader.GetString(7), reader.GetString(8),
                reader.GetDecimal(9), reader.GetDecimal(10), reader.GetDecimal(11), reader.GetDecimal(12),
                reader.GetString(13), reader.GetString(14), reader.GetString(15),
                reader.IsDBNull(16) ? null : reader.GetString(16), reader.GetString(17),
                reader.IsDBNull(18) ? null : reader.GetString(18),
                reader.IsDBNull(19) ? null : reader.GetString(19),
                reader.GetFieldValue<DateTimeOffset>(20), reader.GetFieldValue<DateTimeOffset>(21));
        }
        const string itemsSql = """
            SELECT id, listing_id, product_id, variant_id, item_name, variant_code, sku,
                   unit_price, currency, quantity, discount_total, line_total
            FROM commerce.order_items WHERE order_id = @order_id ORDER BY id
            """;
        await using var itemsCommand = new NpgsqlCommand(itemsSql, connection, transaction);
        itemsCommand.Parameters.AddWithValue("order_id", header.OrderId);
        await using var itemsReader = await itemsCommand.ExecuteReaderAsync(cancellationToken);
        var items = new List<OrderItemRecord>();
        while (await itemsReader.ReadAsync(cancellationToken))
            items.Add(new OrderItemRecord(
                itemsReader.GetGuid(0), itemsReader.GetGuid(1), itemsReader.GetGuid(2), itemsReader.GetGuid(3),
                itemsReader.GetString(4), itemsReader.GetString(5),
                itemsReader.IsDBNull(6) ? null : itemsReader.GetString(6), itemsReader.GetDecimal(7),
                itemsReader.GetString(8), itemsReader.GetInt32(9), itemsReader.GetDecimal(10),
                itemsReader.GetDecimal(11)));
        return new OrderRecord(header.OrderId, header.Number, header.CustomerId, header.VendorId,
            header.VendorName, header.Status, header.PaymentMethod, header.PaymentStatus, header.Currency,
            header.Subtotal, header.Discount, header.DeliveryTotal, header.Total,
            new DeliveryDetails(header.DeliveryName, header.DeliveryPhone, header.Line1, header.Line2,
                header.City, header.Province, header.PostalCode),
            header.PlacedAt, header.UpdatedAt, items);
    }

    private async Task<CommerceWriteResult> ChangeOrderStatusAsync(Guid userId, Guid? vendorId,
        Guid orderId, string nextStatus, bool customerAction, CancellationToken cancellationToken)
    {
        await using var connection = await commerce.DataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(IsolationLevel.Serializable, cancellationToken);
        const string lockSql = """
            SELECT o.status, o.vendor_id
            FROM commerce.orders o
            WHERE o.id = @order_id
              AND ((@customer_action AND o.customer_user_id = @user_id)
                   AND EXISTS (SELECT 1 FROM iam.users cu JOIN iam.user_roles cr ON cr.user_id = cu.id
                               WHERE cu.id = @user_id AND cu.status = 'active'
                                 AND cr.role = 'customer' AND cr.status = 'active')
                   OR (NOT @customer_action AND o.vendor_id = @vendor_id AND EXISTS (
                       SELECT 1 FROM iam.users u JOIN iam.vendor_memberships m ON m.user_id = u.id
                       WHERE u.id = @user_id AND u.status = 'active' AND m.vendor_id = @vendor_id
                         AND m.status = 'active' AND m.role IN ('owner','manager','staff')
                   )))
            FOR UPDATE
            """;
        await using var command = new NpgsqlCommand(lockSql, connection, transaction);
        command.Parameters.AddWithValue("order_id", orderId);
        command.Parameters.AddWithValue("user_id", userId);
        command.Parameters.AddWithValue("customer_action", customerAction);
        command.Parameters.Add("vendor_id", NpgsqlDbType.Uuid).Value = (object?)vendorId ?? DBNull.Value;
        string current;
        Guid actualVendorId;
        await using (var reader = await command.ExecuteReaderAsync(cancellationToken))
        {
            if (!await reader.ReadAsync(cancellationToken)) return CommerceWriteResult.NotFound;
            current = reader.GetString(0);
            actualVendorId = reader.GetGuid(1);
        }
        var allowed = customerAction
            ? nextStatus == "cancelled" && CommerceRules.CanCustomerCancel(current)
            : CommerceRules.CanVendorTransition(current, nextStatus);
        if (!allowed)
        {
            await transaction.RollbackAsync(cancellationToken);
            return CommerceWriteResult.InvalidTransition;
        }

        if (nextStatus is "cancelled" or "completed")
        {
            var stockSql = nextStatus == "cancelled"
                ? """
                  UPDATE inventory.inventory_balances b SET
                    reserved_quantity = b.reserved_quantity - r.quantity, updated_at = now()
                  FROM inventory.inventory_reservations r
                  JOIN commerce.order_items oi ON oi.id = r.order_item_id
                  WHERE oi.order_id = @order_id AND r.listing_id = b.listing_id AND r.status = 'active';
                  UPDATE inventory.inventory_reservations r SET status = 'released', released_at = now(), updated_at = now()
                  FROM commerce.order_items oi WHERE oi.id = r.order_item_id AND oi.order_id = @order_id AND r.status = 'active';
                  """
                : """
                  UPDATE inventory.inventory_balances b SET
                    on_hand_quantity = b.on_hand_quantity - r.quantity,
                    reserved_quantity = b.reserved_quantity - r.quantity, updated_at = now()
                  FROM inventory.inventory_reservations r
                  JOIN commerce.order_items oi ON oi.id = r.order_item_id
                  WHERE oi.order_id = @order_id AND r.listing_id = b.listing_id AND r.status = 'active';
                  UPDATE inventory.inventory_reservations r SET status = 'consumed', consumed_at = now(), updated_at = now()
                  FROM commerce.order_items oi WHERE oi.id = r.order_item_id AND oi.order_id = @order_id AND r.status = 'active';
                  """;
            await using var stock = new NpgsqlCommand(stockSql, connection, transaction);
            stock.Parameters.AddWithValue("order_id", orderId);
            await stock.ExecuteNonQueryAsync(cancellationToken);
        }
        const string updateSql = """
            UPDATE commerce.orders SET status = @status, updated_at = now(),
              cancelled_at = CASE WHEN @status = 'cancelled' THEN now() ELSE cancelled_at END,
              completed_at = CASE WHEN @status = 'completed' THEN now() ELSE completed_at END,
              payment_status = CASE WHEN @status = 'completed' AND payment_method = 'cash_on_delivery'
                                    THEN 'paid' ELSE payment_status END
            WHERE id = @order_id
            """;
        await using var update = new NpgsqlCommand(updateSql, connection, transaction);
        update.Parameters.AddWithValue("status", nextStatus);
        update.Parameters.AddWithValue("order_id", orderId);
        await update.ExecuteNonQueryAsync(cancellationToken);
        await WriteEventAsync(connection, transaction, userId, actualVendorId, orderId,
            "order", $"order.{nextStatus}", cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return CommerceWriteResult.Updated;
    }

    private static async Task WriteEventAsync(NpgsqlConnection connection, NpgsqlTransaction transaction,
        Guid actorId, Guid vendorId, Guid entityId, string entityType, string action,
        CancellationToken cancellationToken)
    {
        const string sql = """
            INSERT INTO audit.audit_log (actor_user_id, vendor_id, entity_type, entity_id, action, after_data)
            VALUES (@actor_id, @vendor_id, @entity_type, @entity_id, @action, @payload::jsonb);
            INSERT INTO integration.outbox_events (event_type, aggregate_type, aggregate_id, payload)
            VALUES (@action, @entity_type, @entity_id, @payload::jsonb);
            """;
        await using var command = new NpgsqlCommand(sql, connection, transaction);
        command.Parameters.AddWithValue("actor_id", actorId);
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("entity_type", entityType);
        command.Parameters.AddWithValue("entity_id", entityId);
        command.Parameters.AddWithValue("action", action);
        command.Parameters.AddWithValue("payload", JsonSerializer.Serialize(new { entityId, vendorId }));
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static void AddDelivery(NpgsqlCommand command, DeliveryDetails delivery)
    {
        command.Parameters.AddWithValue("name", delivery.Name);
        command.Parameters.AddWithValue("phone", delivery.Phone);
        command.Parameters.AddWithValue("line1", delivery.AddressLine1);
        command.Parameters.Add("line2", NpgsqlDbType.Text).Value = (object?)delivery.AddressLine2 ?? DBNull.Value;
        command.Parameters.AddWithValue("city", delivery.City);
        command.Parameters.Add("province", NpgsqlDbType.Text).Value = (object?)delivery.Province ?? DBNull.Value;
        command.Parameters.Add("postal_code", NpgsqlDbType.Text).Value = (object?)delivery.PostalCode ?? DBNull.Value;
    }

    private static void AddAnalyticsParameters(NpgsqlCommand command, Guid vendorId, int periodDays)
    {
        command.Parameters.AddWithValue("vendor_id", vendorId);
        command.Parameters.AddWithValue("period_days", periodDays);
    }

    private static string Fingerprint(PlaceOrder request)
    {
        var canonical = JsonSerializer.SerializeToUtf8Bytes(new
        {
            items = request.Items.OrderBy(item => item.ListingId)
                .Select(item => new { item.ListingId, item.Quantity }),
            request.AcceptedOfferId,
            request.PaymentMethod,
            request.Delivery
        });
        return Convert.ToHexString(SHA256.HashData(canonical)).ToLowerInvariant();
    }

    private sealed record OrderLine(Guid ListingId, Guid VariantId, Guid ProductId, string Name,
        string VariantCode, string? Sku, Guid VendorId, decimal Price, string Currency,
        int OnHand, int Reserved, int Quantity);
    private sealed record OrderHeader(Guid OrderId, string Number, Guid CustomerId, Guid VendorId,
        string VendorName, string Status, string PaymentMethod, string PaymentStatus, string Currency,
        decimal Subtotal, decimal Discount, decimal DeliveryTotal, decimal Total, string DeliveryName,
        string DeliveryPhone, string Line1, string? Line2, string City, string? Province,
        string? PostalCode, DateTimeOffset PlacedAt, DateTimeOffset UpdatedAt);
}

public sealed class UnavailableCommerceStore : ICommerceStore
{
    private static Task<T> Throw<T>() => Task.FromException<T>(new CommerceUnavailableException());
    public Task<IReadOnlyList<OfferRecord>> GetCustomerOffersAsync(Guid a,string? b,int c,CancellationToken d)=>Throw<IReadOnlyList<OfferRecord>>();
    public Task<OfferRecord?> GetCustomerOfferAsync(Guid a,Guid b,CancellationToken c)=>Throw<OfferRecord?>();
    public Task<OfferRecord?> CreateOfferAsync(Guid a,CreateOffer b,CancellationToken c)=>Throw<OfferRecord?>();
    public Task<CommerceWriteResult> WithdrawOfferAsync(Guid a,Guid b,CancellationToken c)=>Throw<CommerceWriteResult>();
    public Task<CommerceWriteResult> AcceptCounterOfferAsync(Guid a,Guid b,CancellationToken c)=>Throw<CommerceWriteResult>();
    public Task<IReadOnlyList<OfferRecord>> GetVendorOffersAsync(Guid a,Guid b,string? c,int d,CancellationToken e)=>Throw<IReadOnlyList<OfferRecord>>();
    public Task<CommerceWriteResult> DecideOfferAsync(Guid a,Guid b,Guid c,VendorOfferDecision d,CancellationToken e)=>Throw<CommerceWriteResult>();
    public Task<OrderRecord?> PlaceOrderAsync(Guid a,PlaceOrder b,CancellationToken c)=>Throw<OrderRecord?>();
    public Task<IReadOnlyList<OrderRecord>> GetCustomerOrdersAsync(Guid a,string? b,int c,CancellationToken d)=>Throw<IReadOnlyList<OrderRecord>>();
    public Task<OrderRecord?> GetCustomerOrderAsync(Guid a,Guid b,CancellationToken c)=>Throw<OrderRecord?>();
    public Task<CommerceWriteResult> CancelCustomerOrderAsync(Guid a,Guid b,CancellationToken c)=>Throw<CommerceWriteResult>();
    public Task<IReadOnlyList<OrderRecord>> GetVendorOrdersAsync(Guid a,Guid b,string? c,int d,CancellationToken e)=>Throw<IReadOnlyList<OrderRecord>>();
    public Task<CommerceWriteResult> TransitionVendorOrderAsync(Guid a,Guid b,Guid c,string d,CancellationToken e)=>Throw<CommerceWriteResult>();
    public Task<VendorCommerceSummary?> GetVendorSummaryAsync(Guid a,Guid b,CancellationToken c)=>Throw<VendorCommerceSummary?>();
    public Task<VendorAnalytics?> GetVendorAnalyticsAsync(Guid a,Guid b,int c,CancellationToken d)=>Throw<VendorAnalytics?>();
}
