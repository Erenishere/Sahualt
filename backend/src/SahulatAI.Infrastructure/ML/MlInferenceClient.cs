using System.Globalization;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.Options;

namespace SahulatAI.Infrastructure.ML;

public sealed class MlInferenceClient(HttpClient httpClient, IOptions<MlInferenceOptions> options)
    : IMlInferenceClient
{
    private const int MaxImageBytes = 20 * 1024 * 1024;
    private const int MaxAudioBytes = 2 * 1024 * 1024;
    private const int MaxResponseBytes = 256 * 1024;
    private const string VoiceModel = "whisper-large-v3";
    private const string VoiceRevision = "06f233fe06e710322aca913c1bc4249a0d71fce1";
    private readonly MlInferenceOptions _options = options.Value;

    public async Task<VisualSearchResponse> SearchImageAsync(
        byte[] image, string mediaType, int topK, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(image);
        if (image.Length is 0 or > MaxImageBytes)
            throw new ArgumentOutOfRangeException(nameof(image));
        if (mediaType is not ("image/jpeg" or "image/png" or "image/webp"))
            throw new ArgumentException("Unsupported image media type.", nameof(mediaType));
        if (topK is < 1 or > 100)
            throw new ArgumentOutOfRangeException(nameof(topK));

        var source = Required(_options.VisualSourceSystem, nameof(_options.VisualSourceSystem));
        var model = Required(_options.VisualModel, nameof(_options.VisualModel));
        var embedding = Required(_options.VisualEmbeddingVersion, nameof(_options.VisualEmbeddingVersion));
        using var form = new MultipartFormDataContent();
        var imageContent = new ByteArrayContent(image);
        imageContent.Headers.ContentType = new MediaTypeHeaderValue(mediaType);
        form.Add(imageContent, "image", "upload");
        form.Add(new StringContent(topK.ToString(CultureInfo.InvariantCulture)), "top_k");
        using var request = new HttpRequestMessage(HttpMethod.Post, Endpoint(_options.VisualBaseUrl, "/api/v1/search/image"))
        { Content = form };
        using var json = await SendJsonAsync(request, cancellationToken);
        try
        {
            var root = json.RootElement;
            if (RequiredString(root, "contract_version") != "visual-http-v1" ||
                RequiredString(root, "identity_scope") != "external" ||
                RequiredString(root, "source_system") != source ||
                RequiredString(root, "model") != model ||
                RequiredString(root, "embedding_version") != embedding)
                throw new MlInferenceException("Visual service identity mismatch.");

            var results = root.GetProperty("results");
            if (results.ValueKind != JsonValueKind.Array || results.GetArrayLength() > topK)
                throw new MlInferenceException("Invalid visual result list.");
            var matches = new List<ExternalVisualMatch>(results.GetArrayLength());
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var item in results.EnumerateArray())
            {
                var productId = RequiredString(item, "product_id");
                var imageId = RequiredString(item, "matched_image_id");
                var score = item.GetProperty("score").GetDouble();
                if (!double.IsFinite(score) || !seen.Add(productId))
                    throw new MlInferenceException("Invalid visual result.");
                matches.Add(new ExternalVisualMatch(productId, score, imageId));
            }
            return new VisualSearchResponse(source, model, embedding, matches);
        }
        catch (Exception exception) when (exception is JsonException or InvalidOperationException or KeyNotFoundException or FormatException)
        {
            throw new MlInferenceException("Invalid visual service response.");
        }
    }

    public async Task<VoiceTranscription> TranscribeAsync(
        byte[] audio, string language, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(audio);
        if (audio.Length is 0 or > MaxAudioBytes)
            throw new ArgumentOutOfRangeException(nameof(audio));
        if (language is not ("en" or "ur"))
            throw new ArgumentException("This language is not enabled for serving.", nameof(language));

        using var request = new HttpRequestMessage(HttpMethod.Post, Endpoint(_options.VoiceBaseUrl, "/api/v1/transcriptions"))
        { Content = new ByteArrayContent(audio) };
        request.Content.Headers.ContentType = new MediaTypeHeaderValue("audio/wav");
        request.Headers.Add("X-Voice-Language", language);
        using var json = await SendJsonAsync(request, cancellationToken);
        try
        {
            var root = json.RootElement;
            var checksum = RequiredString(root, "transcript_checksum");
            var audioHash = RequiredString(root, "audio_sha256");
            if (RequiredString(root, "contract_version") != "voice-http-v1" ||
                RequiredString(root, "language") != language ||
                RequiredString(root, "model") != VoiceModel ||
                RequiredString(root, "revision") != VoiceRevision ||
                audioHash != Convert.ToHexStringLower(SHA256.HashData(audio)) ||
                checksum.Length != 71 || !checksum.StartsWith("sha256:", StringComparison.Ordinal) ||
                !IsLowerHex(checksum.AsSpan(7)))
                throw new MlInferenceException("Voice service identity mismatch.");

            var text = RequiredString(root, "text");
            if (text.Length > 2048)
                throw new MlInferenceException("Invalid voice transcript.");
            return new VoiceTranscription(language, text, VoiceModel, VoiceRevision, audioHash, checksum);
        }
        catch (Exception exception) when (exception is JsonException or InvalidOperationException or KeyNotFoundException or FormatException)
        {
            throw new MlInferenceException("Invalid voice service response.");
        }
    }

    private async Task<JsonDocument> SendJsonAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        using var response = await httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        if (!response.IsSuccessStatusCode)
            throw new MlInferenceException($"ML service returned HTTP {(int)response.StatusCode}.");
        if (response.Content.Headers.ContentType?.MediaType != "application/json" ||
            response.Content.Headers.ContentLength > MaxResponseBytes)
            throw new MlInferenceException("Invalid ML service response headers.");

        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        using var buffer = new MemoryStream();
        var chunk = new byte[8192];
        int count;
        while ((count = await stream.ReadAsync(chunk, cancellationToken)) != 0)
        {
            if (buffer.Length + count > MaxResponseBytes)
                throw new MlInferenceException("ML service response is too large.");
            buffer.Write(chunk, 0, count);
        }
        try
        {
            return JsonDocument.Parse(buffer.ToArray());
        }
        catch (JsonException)
        {
            throw new MlInferenceException("Invalid ML service JSON.");
        }
    }

    private static string RequiredString(JsonElement obj, string name)
    {
        var value = obj.GetProperty(name).GetString();
        if (string.IsNullOrWhiteSpace(value))
            throw new MlInferenceException("Missing ML service response field.");
        return value;
    }

    private static string Required(string? value, string name) =>
        string.IsNullOrWhiteSpace(value) ? throw new InvalidOperationException($"MlServices:{name} is required.") : value;

    private static Uri Endpoint(string? baseUrl, string path)
    {
        var value = Required(baseUrl, "BaseUrl");
        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri) ||
            uri.Scheme is not ("http" or "https") || uri.UserInfo.Length != 0 ||
            uri.AbsolutePath != "/" || uri.Query.Length != 0 || uri.Fragment.Length != 0 ||
            (uri.Scheme == "http" && !uri.IsLoopback))
            throw new InvalidOperationException("ML service URL must be HTTPS or loopback HTTP without a path.");
        return new Uri(uri, path);
    }

    private static bool IsLowerHex(ReadOnlySpan<char> text)
    {
        foreach (var character in text)
            if (character is not (>= '0' and <= '9' or >= 'a' and <= 'f'))
                return false;
        return true;
    }
}
