import copy
from dataclasses import replace

import pytest

from sahulat_voice.adapters import HuggingFaceAdapter
from sahulat_voice.benchmark.io import put_json, read_json, record_checksum
from sahulat_voice.contracts import MODEL_SPECS, Language, RuntimeSettings
from sahulat_voice.errors import ErrorCode, VoiceError
from sahulat_voice.evaluation import EvaluationInput, EvaluationSample
from sahulat_voice.runs import execution
from sahulat_voice.runs.scoring import score, summarize
from sahulat_voice.service import TranscriptionService


class TestAdapter(HuggingFaceAdapter):
    __test__ = False
    spec = MODEL_SPECS["whisper"]

    def __init__(self, raw="Human fixture", error=None):
        super().__init__(RuntimeSettings())
        self.raw = raw
        self.error = error
        self.calls = []
        self.loads = 0
        self.languages = []

    def _load(self):
        self.loads += 1
        if self.error == "load":
            raise VoiceError(ErrorCode.MODEL_UNAVAILABLE)

    def _prepare_language(self, language):
        self.languages.append(language)

    def _infer(self, audio, language):
        return self.raw

    def transcribe(self, audio, language):
        self.calls.append(language)
        if self.error == "inference":
            raise VoiceError(ErrorCode.INFERENCE_FAILED)
        return self.raw


@pytest.fixture
def run_input(tmp_path, wav_bytes, monkeypatch):
    # Pure synthetic runner fixtures; never written to the real benchmark artifact root.
    import hashlib

    bundle = tmp_path / execution.ARTIFACT_PATH
    bundle.mkdir(parents=True)
    samples = []
    for language in Language:
        path = f"{language.value}.wav"
        (bundle / path).write_bytes(wav_bytes)
        samples.append(
            EvaluationSample(
                f"test_{language.value}",
                language,
                path,
                hashlib.sha256(wav_bytes).hexdigest(),
                "Human fixture",
                "test:human",
                "human_recording",
            )
        )
    inputs = EvaluationInput(tuple(sorted(samples, key=lambda s: s.sample_id)), "test")
    descriptor = {"manifest_sha256": execution.EXPECTED_MANIFEST, "sample_count": 4}
    monkeypatch.setattr(execution, "verified_input", lambda root: (descriptor, inputs))
    monkeypatch.setattr(execution, "environment", lambda: {"device": "cpu", "dtype": "float32"})
    monkeypatch.setattr(execution, "implementation", lambda root: {"test": "synthetic"})
    monkeypatch.setattr(
        execution, "acquired_assets", lambda root, name, check_cache: {"test": name}
    )
    return tmp_path, bundle, inputs


def test_frozen_primary_view_not_strict_or_clamped():
    assert score("Hello, WORLD!", "hello world")["wer"] == 0
    assert score("one", "one two three")["wer"] == 2
    assert score("اُردو", "اردو")["cer"] > 0


def test_invalid_reference_blocks_scoring():
    with pytest.raises(VoiceError):
        score("...", "anything")


def test_scoring_does_not_apply_second_nfc_after_casefold():
    result = score("\u0390", "\u03b9")
    assert result["reference_characters"] == 3
    assert result["character_errors"] == 2


def test_casefold_expansion_not_subject_to_second_raw_transcript_limit():
    result = score("\u0130" * 1025, "")
    assert result["reference_characters"] == 2050
    assert result["cer"] == 1


@pytest.mark.parametrize("raw", ["", "  ", "\ud800"])
def test_invalid_decoder_output_retained_as_failure(run_input, raw):
    _, bundle, inputs = run_input
    service = TranscriptionService(execution.CaptureAdapter(TestAdapter(raw)))
    record = execution.sample_call(service, inputs.samples[0], bundle)
    assert record["status"] == "FAILED"
    assert record["transcript"] is None
    assert record["scoring"]["wer"] == record["scoring"]["cer"] == 1
    assert record["raw_decoder_output"] == (None if raw == "\ud800" else raw)
    if raw == "\ud800":
        assert record["raw_decoder_codepoints_if_invalid_utf8"] == [0xD800]
    assert record_checksum(record)


def test_success_raw_normalized_checksum_and_timing_separation(run_input):
    _, bundle, inputs = run_input
    adapter = TestAdapter("  Human\nfixture  ")
    record = execution.sample_call(
        TranscriptionService(execution.CaptureAdapter(adapter)), inputs.samples[0], bundle
    )
    assert record["raw_decoder_output"] == "  Human\nfixture  "
    assert record["transcript"]["text"] == "Human fixture"
    assert record["scoring"]["wer"] == 0
    assert "timing" not in record["transcript"]


def test_inference_failure_counts_deletions_without_retry(run_input):
    _, bundle, inputs = run_input
    adapter = TestAdapter(error="inference")
    record = execution.sample_call(
        TranscriptionService(execution.CaptureAdapter(adapter)), inputs.samples[0], bundle
    )
    assert record["failure_code"] == "inference_failed"
    assert record["raw_decoder_output"] is None
    assert record["scoring"]["wer"] == 1
    assert len(adapter.calls) == 1


def test_warmup_and_scored_calls_exactly_once_per_language(run_input, monkeypatch):
    root, _, inputs = run_input
    adapter = TestAdapter()
    monkeypatch.setattr(execution, "create_adapter", lambda *args: adapter)
    path = root / "results/whisper.json"
    result = execution.execute_model(root, path, "whisper")
    assert adapter.loads == 1
    assert adapter.languages == list(Language)
    assert len(adapter.calls) == 8  # Four mandated unscored warmups plus four scored calls.
    assert result["summary"]["overall"]["successful_samples"] == 4
    assert len(result["records"]) == len(inputs.samples)
    assert execution.verify_model(root, path, "whisper")["status"] == "VERIFIED"
    with pytest.raises(VoiceError):
        execution.execute_model(root, path, "whisper")


def test_load_failure_has_no_repeated_model_attempts_or_fake_transcripts(run_input, monkeypatch):
    root, _, _ = run_input
    adapter = TestAdapter(error="load")
    monkeypatch.setattr(execution, "create_adapter", lambda *args: adapter)
    result = execution.execute_model(root, root / "results/whisper.json", "whisper")
    assert adapter.loads == 1 and not adapter.calls
    assert result["status"] == "LOAD_FAILED"
    assert result["summary"]["overall"]["failed_samples"] == 4
    assert result["summary"]["overall"]["wer"] == 1
    assert all(
        record["transcript"] is None and record["timing"] is None for record in result["records"]
    )


@pytest.mark.parametrize("field", ["audio_sha256", "language", "raw_decoder_output", "scoring"])
def test_evidence_tampering_rejected(run_input, monkeypatch, field):
    root, _, _ = run_input
    monkeypatch.setattr(execution, "create_adapter", lambda *args: TestAdapter())
    path = root / "results/whisper.json"
    execution.execute_model(root, path, "whisper")
    result = read_json(path)
    result["records"][0][field] = "tampered"
    changed = root / "tampered.json"
    put_json(changed, result)
    with pytest.raises((VoiceError, TypeError)):
        execution.verify_model(root, changed, "whisper")


def test_semantic_hash_ignores_timing_but_changes_with_decoder(run_input):
    _, bundle, inputs = run_input
    record = execution.sample_call(
        TranscriptionService(execution.CaptureAdapter(TestAdapter())), inputs.samples[0], bundle
    )
    semantic = {key: value for key, value in record.items() if key != "timing"}
    changed = copy.deepcopy(record)
    changed["timing"]["stt_ms"] = 999999
    assert record_checksum(semantic) == record_checksum(
        {key: value for key, value in changed.items() if key != "timing"}
    )
    changed["raw_decoder_output"] = "different"
    assert record_checksum(semantic) != record_checksum(
        {key: value for key, value in changed.items() if key != "timing"}
    )


def test_macro_averages_language_micro_rates_and_missing_timings_not_zero(run_input):
    _, bundle, inputs = run_input
    records = [
        execution.unavailable_sample(sample, bundle, "whisper", "model_unavailable", "base_load")
        for sample in inputs.samples
    ]
    records[0]["status"] = "SUCCESS"
    records[0]["scoring"] = score("Human fixture", "Human fixture")
    result = summarize(records)
    assert result["overall"]["wer"] == 0.75
    assert all(group["latency"]["stt_ms"] is None for group in result["languages"].values())


def test_dataset_integrity_failure_prevents_adapter_creation(monkeypatch, tmp_path):
    def fail(root):
        raise VoiceError(ErrorCode.CHECKSUM_MISMATCH)

    monkeypatch.setattr(execution, "verify_frozen", fail)
    with pytest.raises(VoiceError):
        execution.execute_model(tmp_path, tmp_path / "result.json", "whisper")
    assert not (tmp_path / "result.json").exists()


def test_expected_manifest_mismatch_fails_before_loading_inputs(monkeypatch, tmp_path):
    monkeypatch.setattr(execution, "verify_frozen", lambda root: {"manifest_sha256": "0" * 64})
    with pytest.raises(VoiceError):
        execution.verified_input(tmp_path)


def test_unscored_warmup_uses_first_seeded_selection_not_artifact_order(run_input):
    import hashlib

    _, _, inputs = run_input
    sample = next(s for s in inputs.samples if s.language == Language.ENGLISH)
    samples = [replace(sample, sample_id=f"sample_{i}", audio_path=f"{i}.wav") for i in range(8)]
    expected = min(
        samples,
        key=lambda s: hashlib.sha256(
            f"EVAL-VOICE-V1|20260912|en_us|{s.audio_path}".encode()
        ).hexdigest(),
    )
    assert execution.first_selected(samples) == expected
    assert execution.first_selected(list(reversed(samples))) == expected
