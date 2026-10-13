namespace SahulatAI.Application.Features.Marketplace;

public sealed class CatalogSearchOptions
{
    public const string SectionName = "CatalogSearch";

    public string TextCorpusSha256 { get; init; } =
        "5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f";

    public string TextSearchConfig { get; init; } = "english";
}
