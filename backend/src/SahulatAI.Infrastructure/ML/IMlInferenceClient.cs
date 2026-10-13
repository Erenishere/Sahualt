namespace SahulatAI.Infrastructure.ML;

public interface IMlInferenceClient
{
    Task<VisualSearchResponse> SearchImageAsync(
        byte[] image, string mediaType, int topK, CancellationToken cancellationToken = default);

    Task<VoiceTranscription> TranscribeAsync(
        byte[] audio, string language, CancellationToken cancellationToken = default);
}
