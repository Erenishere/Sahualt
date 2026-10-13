using System.Net;
using System.Security.Cryptography;
using System.Text;
using SahulatAI.Infrastructure.ML;

namespace SahulatAI.UnitTests;

public sealed class MlInferenceClientTests
{
    private static readonly MlInferenceOptions Options = new()
    {
        VisualBaseUrl = "http://127.0.0.1:8000/",
        VisualSourceSystem = "vendor-catalog-v1",
        VisualModel = "openclip",
        VisualEmbeddingVersion = "embedding-v1",
        VoiceBaseUrl = "http://127.0.0.1:8001/"
    };

    [Fact]
    public async Task ImageRequestUsesMultipartContractAndKeepsExternalIdentity()
    {
        var handler = new StubHandler(async request =>
        {
            Assert.Equal("/api/v1/search/image", request.RequestUri!.AbsolutePath);
            Assert.Equal("multipart/form-data", request.Content!.Headers.ContentType!.MediaType);
            var body = await request.Content.ReadAsStringAsync();
            Assert.Contains("name=image", body);
            Assert.Contains("name=top_k", body);
            return Json("""
                {"contract_version":"visual-http-v1","identity_scope":"external","source_system":"vendor-catalog-v1","model":"openclip","embedding_version":"embedding-v1","results":[{"product_id":"external-42","matched_image_id":"img-1","score":0.75}]}
                """);
        });
        var result = await Client(handler).SearchImageAsync([1, 2, 3], "image/png", 1);

        Assert.Equal("vendor-catalog-v1", result.SourceSystem);
        Assert.Equal("external-42", Assert.Single(result.Matches).ExternalProductId);
    }

    [Fact]
    public async Task VoiceRequestUsesRawWavAndChecksAudioHash()
    {
        byte[] audio = [1, 2, 3];
        var hash = Convert.ToHexStringLower(SHA256.HashData(audio));
        var handler = new StubHandler(async request =>
        {
            Assert.Equal("/api/v1/transcriptions", request.RequestUri!.AbsolutePath);
            Assert.Equal("audio/wav", request.Content!.Headers.ContentType!.MediaType);
            Assert.Equal("ur", Assert.Single(request.Headers.GetValues("X-Voice-Language")));
            Assert.Equal(audio, await request.Content.ReadAsByteArrayAsync());
            return Json($$"""
                {"contract_version":"voice-http-v1","language":"ur","text":"سلام","model":"whisper-large-v3","revision":"06f233fe06e710322aca913c1bc4249a0d71fce1","audio_sha256":"{{hash}}","transcript_checksum":"sha256:{{new string('a', 64)}}"}
                """);
        });
        var result = await Client(handler).TranscribeAsync(audio, "ur");

        Assert.Equal("سلام", result.Text);
        Assert.Equal(hash, result.AudioSha256);
    }

    [Fact]
    public async Task RejectsVisualResponseWithDifferentSource()
    {
        var handler = new StubHandler(_ => Task.FromResult(Json("""
            {"contract_version":"visual-http-v1","identity_scope":"external","source_system":"different","model":"openclip","embedding_version":"embedding-v1","results":[]}
            """)));
        await Assert.ThrowsAsync<MlInferenceException>(() =>
            Client(handler).SearchImageAsync([1], "image/png", 5));
    }

    [Fact]
    public async Task RejectsUnsupportedVoiceLanguageBeforeNetwork()
    {
        var handler = new StubHandler(_ => throw new Exception("Network must not be called"));
        await Assert.ThrowsAsync<ArgumentException>(() => Client(handler).TranscribeAsync([1], "sd"));
    }

    [Fact]
    public async Task RejectsVoiceResponseForDifferentAudio()
    {
        var handler = new StubHandler(_ => Task.FromResult(Json($$"""
            {"contract_version":"voice-http-v1","language":"en","text":"hello","model":"whisper-large-v3","revision":"06f233fe06e710322aca913c1bc4249a0d71fce1","audio_sha256":"{{new string('0', 64)}}","transcript_checksum":"sha256:{{new string('a', 64)}}"}
            """)));
        await Assert.ThrowsAsync<MlInferenceException>(() => Client(handler).TranscribeAsync([1], "en"));
    }

    [Fact]
    public async Task RejectsOversizedResponse()
    {
        var handler = new StubHandler(_ => Task.FromResult(Json(new string('a', 256 * 1024 + 1))));
        await Assert.ThrowsAsync<MlInferenceException>(() =>
            Client(handler).SearchImageAsync([1], "image/png", 5));
    }

    private static MlInferenceClient Client(HttpMessageHandler handler) =>
        new(new HttpClient(handler), Microsoft.Extensions.Options.Options.Create(Options));

    private static HttpResponseMessage Json(string value) => new(HttpStatusCode.OK)
    {
        Content = new StringContent(value, Encoding.UTF8, "application/json")
    };

    private sealed class StubHandler(Func<HttpRequestMessage, Task<HttpResponseMessage>> send) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken cancellationToken) => send(request);
    }
}
