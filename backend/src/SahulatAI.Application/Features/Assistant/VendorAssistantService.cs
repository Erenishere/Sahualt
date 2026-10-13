using System.Text.RegularExpressions;

namespace SahulatAI.Application.Features.Assistant;

public sealed class VendorAssistantService(IVendorCatalogReader catalogReader, TimeProvider timeProvider)
{
    private const int ResultLimit = 20;
    private const int LowStockThreshold = 5;

    public async Task<AssistantAnswer> AnswerAsync(
        Guid userId,
        Guid vendorId,
        AssistantQuery query,
        CancellationToken cancellationToken)
    {
        var correlationId = Guid.NewGuid();
        var question = Regex.Replace(query.Question.Trim().ToLowerInvariant(), @"\s+", " ");
        var intent = Classify(question);

        if (intent is null)
        {
            return new AssistantAnswer(
                "I can answer questions about your listings, stock, prices, and publication requirements. Sales and order information is not available yet.",
                "unsupported", "unsupported", [], correlationId);
        }

        if (intent is (CatalogQuestion.ListingDetails or CatalogQuestion.PublicationBlockers) && query.ProductId is null)
        {
            return new AssistantAnswer(
                "Choose a product so I can check its current listing and publication details.",
                IntentCode(intent.Value), "needs_clarification", [], correlationId);
        }

        var observedAt = timeProvider.GetUtcNow();
        if (intent == CatalogQuestion.DraftProducts)
        {
            var products = await catalogReader.GetDraftProductsAsync(userId, vendorId, ResultLimit, cancellationToken);
            var names = string.Join("; ", products.Items.Select(product => product.ProductName));
            var answer = $"You have {products.Total} draft products." +
                (products.Items.Count == 0 ? "" : $" Showing up to {ResultLimit}: {names}.");
            var sources = products.Items.Select(product =>
                new AssistantEvidence("product", product.ProductId, product.ProductName, observedAt, product.ProductId)).ToArray();
            return new AssistantAnswer(answer, IntentCode(intent.Value), "answered", sources, correlationId);
        }

        if (intent == CatalogQuestion.PublicationBlockers)
        {
            var facts = await catalogReader.GetPublicationFactsAsync(userId, vendorId, query.ProductId!.Value, cancellationToken);
            if (facts is null)
            {
                return new AssistantAnswer("I couldn't find that product in your catalog.",
                    IntentCode(intent.Value), "not_found", [], correlationId);
            }

            var blockers = new List<string>();
            if (!facts.HasCategory) blockers.Add("an active category is missing");
            if (!facts.HasActiveImage) blockers.Add("an active image is missing");
            if (!facts.HasActiveDefaultVariant) blockers.Add("an active default variant is missing");
            if (!facts.HasCompleteListing) blockers.Add("a listing with price, currency, and known availability is missing");

            var answer = blockers.Count == 0
                ? $"{facts.ProductName} meets the catalog requirements checked here. Publishing still requires the normal backend workflow."
                : $"{facts.ProductName} has these publication blockers: {string.Join("; ", blockers)}.";
            return new AssistantAnswer(answer, IntentCode(intent.Value), "answered",
                [new AssistantEvidence("product", facts.ProductId, facts.ProductName, observedAt, facts.ProductId)], correlationId);
        }

        var page = await catalogReader.GetListingsAsync(userId, vendorId, intent.Value, query.ProductId,
            LowStockThreshold, ResultLimit, cancellationToken);
        var evidence = page.Items.Select(item =>
            new AssistantEvidence("listing", item.ListingId, item.ProductName, observedAt, item.ProductId)).ToArray();

        if (intent == CatalogQuestion.ListingDetails && page.Total == 0)
        {
            return new AssistantAnswer("I couldn't find a listing for that product in your catalog.",
                IntentCode(intent.Value), "not_found", [], correlationId);
        }

        var noun = page.Total == 1 ? "listing" : "listings";
        var label = intent switch
        {
            CatalogQuestion.ActiveListings => $"active {noun}",
            CatalogQuestion.DraftListings => $"draft {noun}",
            CatalogQuestion.LowStock => $"active {noun} with 0-{LowStockThreshold} available units",
            CatalogQuestion.UnknownStock => $"active {noun} with unknown stock",
            _ => noun
        };
        var lines = page.Items.Select(item => FormatListing(item, intent.Value)).ToArray();
        var summary = intent == CatalogQuestion.ListingDetails
            ? string.Join(" ", lines)
            : $"You have {page.Total} {label}." + (lines.Length == 0 ? "" : $" Showing up to {ResultLimit}: {string.Join("; ", lines)}.");

        return new AssistantAnswer(summary, IntentCode(intent.Value), "answered", evidence, correlationId);
    }

    public static CatalogQuestion? Classify(string question)
    {
        if (Has(question, "sales", "sold", "revenue", "order", "profit", "conversion", "refund", "offer", "best-selling"))
            return null;
        if (question.Contains("stock", StringComparison.Ordinal))
        {
            if (Has(question, "unknown", "missing")) return CatalogQuestion.UnknownStock;
            if (Has(question, "low", "running out")) return CatalogQuestion.LowStock;
        }
        if (Has(question, "publish", "publication")) return CatalogQuestion.PublicationBlockers;
        if (Has(question, "price", "availability")) return CatalogQuestion.ListingDetails;
        if (question.Contains("draft", StringComparison.Ordinal))
            return question.Contains("product", StringComparison.Ordinal)
                ? CatalogQuestion.DraftProducts : CatalogQuestion.DraftListings;
        if (question.Contains("active", StringComparison.Ordinal) && Has(question, "listing", "product"))
            return CatalogQuestion.ActiveListings;
        return null;
    }

    private static bool Has(string text, params string[] terms) =>
        terms.Any(term => text.Contains(term, StringComparison.Ordinal));

    private static string IntentCode(CatalogQuestion question) => question switch
    {
        CatalogQuestion.ActiveListings => "active_listings",
        CatalogQuestion.DraftListings => "draft_listings",
        CatalogQuestion.DraftProducts => "draft_products",
        CatalogQuestion.LowStock => "low_stock",
        CatalogQuestion.UnknownStock => "unknown_stock",
        CatalogQuestion.ListingDetails => "listing_details",
        CatalogQuestion.PublicationBlockers => "publication_blockers",
        _ => throw new ArgumentOutOfRangeException(nameof(question))
    };

    private static string FormatListing(ListingFact item, CatalogQuestion question)
    {
        if (question == CatalogQuestion.ListingDetails)
        {
            var price = item.Price is null || item.Currency is null
                ? "price unknown" : $"{item.Price.Value:0.00} {item.Currency}";
            return $"{item.ProductName}: {price}, availability {item.Availability}, stock " +
                (item.OnHandQuantity is null ? "unknown" : $"{item.OnHandQuantity - item.ReservedQuantity} available") + ".";
        }
        return item.ProductName;
    }
}
