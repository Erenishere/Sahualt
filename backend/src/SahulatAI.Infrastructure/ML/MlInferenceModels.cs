namespace SahulatAI.Infrastructure.ML;

// These IDs come from the visual index and must be resolved against the catalog
// before a customer-facing response can be built.
public sealed record ExternalVisualMatch(string ExternalProductId, double Score, string ExternalImageId);

public sealed record VisualSearchResponse(
    string SourceSystem, string Model, string EmbeddingVersion, IReadOnlyList<ExternalVisualMatch> Matches);

public sealed record VoiceTranscription(
    string Language, string Text, string Model, string Revision, string AudioSha256, string TranscriptChecksum);

public sealed class MlInferenceException(string message) : Exception(message);
