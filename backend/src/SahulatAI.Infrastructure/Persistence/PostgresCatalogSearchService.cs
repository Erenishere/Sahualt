using Microsoft.Extensions.Options;
using Npgsql;
using SahulatAI.Application.Features.Marketplace;
using SahulatAI.Infrastructure.ML;

namespace SahulatAI.Infrastructure.Persistence;

public sealed class PostgresCatalogSearchService(
    NpgsqlDataSource reader,
    IPublicCatalogReader catalog,
    IMlInferenceClient ml,
    IOptions<MlInferenceOptions> mlOptions,
    IOptions<CatalogSearchOptions> searchOptions) : ICatalogSearchService
{
    public async Task<CatalogSearchPage> SearchAsync(
        string? query,
        string mode,
        string? category,
        string? vendorSlug,
        int limit,
        CancellationToken cancellationToken)
    {
        var normalized = string.IsNullOrWhiteSpace(query) ? null : query.Trim();
        if (limit is < 1 or > 50) limit = 24;

        if (mode is "semantic" or "hybrid" && normalized is not null)
        {
            var ids = await SemanticProductIdsAsync(normalized, limit * 2, cancellationToken);
            if (ids.Count > 0)
            {
                var items = await FilterSummariesAsync(ids, category, vendorSlug, limit, cancellationToken);
                if (items.Count > 0)
                    return new CatalogSearchPage(mode, normalized, items, null);
            }
        }

        var page = await catalog.SearchAsync(normalized, category, vendorSlug, null, limit, cancellationToken);
        return new CatalogSearchPage(mode == "semantic" ? "keyword-fallback" : mode, normalized, page.Items, page.NextAfter);
    }

    public async Task<CatalogSearchPage> SearchByImageAsync(
        byte[] image,
        string mediaType,
        int limit,
        CancellationToken cancellationToken)
    {
        if (limit is < 1 or > 50) limit = 24;
        var visual = await ml.SearchImageAsync(image, mediaType, Math.Min(limit, 50), cancellationToken);
        var source = mlOptions.Value.VisualSourceSystem
            ?? throw new MlInferenceException("Visual source system is not configured.");
        var ids = await ResolveExternalProductIdsAsync(
            source, visual.Matches.Select(m => m.ExternalProductId).ToArray(), cancellationToken);
        var items = await catalog.ListSummariesByProductIdsAsync(ids.Take(limit).ToArray(), cancellationToken);
        return new CatalogSearchPage("image", null, items, null);
    }

    public async Task<CatalogSearchPage> SearchByVoiceAsync(
        byte[] audio,
        string language,
        int limit,
        CancellationToken cancellationToken)
    {
        var transcript = await ml.TranscribeAsync(audio, language, cancellationToken);
        return await SearchAsync(transcript.Text, "semantic", null, null, limit, cancellationToken);
    }

    private async Task<List<Guid>> SemanticProductIdsAsync(string query, int limit, CancellationToken cancellationToken)
    {
        var corpus = searchOptions.Value.TextCorpusSha256;
        var config = searchOptions.Value.TextSearchConfig;
        const string sql = """
            WITH parsed AS (
                SELECT websearch_to_tsquery(@config::regconfig, @query) AS tsq
            ),
            ranked AS (
                SELECT lower(d.product_id::text) AS pid,
                       ts_rank_cd(d.document_tsvector, p.tsq) AS score
                FROM search.product_text_lexical_v1 d
                CROSS JOIN parsed p
                WHERE d.corpus_sha256 = @corpus
                  AND d.document_tsvector @@ p.tsq
                ORDER BY score DESC, pid ASC
                LIMIT @limit
            )
            SELECT pid FROM ranked
            """;
        try
        {
            await using var command = reader.CreateCommand(sql);
            command.Parameters.AddWithValue("config", config);
            command.Parameters.AddWithValue("query", query);
            command.Parameters.AddWithValue("corpus", corpus);
            command.Parameters.AddWithValue("limit", limit);
            await using var result = await command.ExecuteReaderAsync(cancellationToken);
            var ids = new List<Guid>();
            while (await result.ReadAsync(cancellationToken))
            {
                if (Guid.TryParse(result.GetString(0), out var id))
                    ids.Add(id);
            }
            return ids;
        }
        catch (PostgresException error) when (error.SqlState == PostgresErrorCodes.UndefinedTable)
        {
            return [];
        }
    }

    private async Task<List<Guid>> ResolveExternalProductIdsAsync(
        string sourceSystem,
        IReadOnlyList<string> externalIds,
        CancellationToken cancellationToken)
    {
        if (externalIds.Count == 0) return [];
        const string sql = """
            SELECT r.external_product_id, p.id
            FROM catalog.product_external_refs r
            JOIN catalog.products p ON p.id = r.product_id
            JOIN catalog.vendors v ON v.id = p.vendor_id
            WHERE r.source_system = @source
              AND r.external_product_id = ANY(@external_ids)
              AND p.status = 'published' AND p.archived_at IS NULL
              AND v.status = 'active'
            """;
        var map = new Dictionary<string, Guid>(StringComparer.Ordinal);
        await using (var command = reader.CreateCommand(sql))
        {
            command.Parameters.AddWithValue("source", sourceSystem);
            command.Parameters.AddWithValue("external_ids", externalIds.ToArray());
            await using var result = await command.ExecuteReaderAsync(cancellationToken);
            while (await result.ReadAsync(cancellationToken))
                map[result.GetString(0)] = result.GetGuid(1);
        }

        const string directSql = """
            SELECT p.id FROM catalog.products p
            JOIN catalog.vendors v ON v.id = p.vendor_id
            WHERE p.id = @id AND p.status = 'published' AND p.archived_at IS NULL AND v.status = 'active'
            """;
        var ordered = new List<Guid>();
        foreach (var external in externalIds)
        {
            if (map.TryGetValue(external, out var mapped))
            {
                ordered.Add(mapped);
                continue;
            }
            if (!Guid.TryParse(external, out var productId)) continue;
            await using var direct = reader.CreateCommand(directSql);
            direct.Parameters.AddWithValue("id", productId);
            var scalar = await direct.ExecuteScalarAsync(cancellationToken);
            if (scalar is Guid resolved)
                ordered.Add(resolved);
        }
        return ordered;
    }

    private async Task<IReadOnlyList<PublicProductSummary>> FilterSummariesAsync(
        IReadOnlyList<Guid> orderedIds,
        string? category,
        string? vendorSlug,
        int limit,
        CancellationToken cancellationToken)
    {
        var summaries = await catalog.ListSummariesByProductIdsAsync(orderedIds, cancellationToken);
        var filtered = summaries.Where(item =>
            (string.IsNullOrWhiteSpace(category) ||
             string.Equals(item.Category, category.Trim(), StringComparison.OrdinalIgnoreCase)) &&
            (string.IsNullOrWhiteSpace(vendorSlug) ||
             string.Equals(item.VendorSlug, vendorSlug.Trim(), StringComparison.OrdinalIgnoreCase)))
            .Take(limit)
            .ToArray();
        return filtered;
    }
}
