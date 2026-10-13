namespace SahulatAI.Infrastructure.ML;

public sealed class MlInferenceOptions
{
    public const string SectionName = "MlServices";

    public string? VisualBaseUrl { get; init; }
    public string? VisualSourceSystem { get; init; }
    public string? VisualModel { get; init; }
    public string? VisualEmbeddingVersion { get; init; }
    public string? VoiceBaseUrl { get; init; }
}
