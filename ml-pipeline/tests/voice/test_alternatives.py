import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from sahulat_voice.alternatives import holdout, metadata, runner
from sahulat_voice.alternatives.adapters import SpecialistWhisperAdapter
from sahulat_voice.benchmark.io import put_json, read_json, record_checksum
from sahulat_voice.contracts import MODEL_SPECS, Language
from sahulat_voice.errors import ErrorCode, VoiceError
from sahulat_voice.evaluation import EvaluationSample
from sahulat_voice.runs.scoring import score
from sahulat_voice.service import TranscriptionService

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def alt_root(tmp_path):
    target = tmp_path / metadata.CONFIG
    target.parent.mkdir(parents=True)
    target.write_bytes((ROOT / metadata.CONFIG).read_bytes())
    return tmp_path


@pytest.fixture
def official():
    # Minimal synthetic publisher metadata, not benchmark/model-quality evidence.
    record = copy.deepcopy(metadata.candidates(ROOT)["pashto-ghag"])
    readme = b"Training data: Common Voice validated speech."
    record["readme_blob_id"] = hashlib.sha1(f"blob {len(readme)}\0".encode() + readme).hexdigest()
    meta = {
        "sha": record["revision"],
        "id": record["repository"],
        "cardData": {
            "license": record["license"],
            "base_model": record["base_model"],
            "language": ["ps"],
            "datasets": record["declared_datasets"],
        },
        "siblings": [
            {
                "rfilename": "model.safetensors",
                "size": record["weights_bytes"],
                "lfs": {"sha256": record["weights_sha256"]},
            }
        ],
    }
    return record, meta, readme


def test_exact_pins_licenses_provenance_and_no_production_router():
    records = metadata.candidates(ROOT)
    assert records["pashto-ghag"]["revision"] == "ed20e00d47d0852ed24f07b4370c0bdac2e5f241"
    assert records["buzzasr-sindhi"]["revision"] == "8e85f09a5c0b17c635ffa8fd124b1efa56fcb5c7"
    assert records["buzzasr-sindhi"]["fleurs_training_declared"] is True
    assert records["buzzasr-sindhi"]["reason"] == "model training includes FLEURS"
    assert all(r["evaluation_independence"] is False for r in records.values())
    assert set(MODEL_SPECS) == {"whisper", "mms"}


def test_official_metadata_roundtrip(official):
    metadata.validate_official(*official)


def test_official_metadata_preserves_verified_snapshot_when_api_counters_change(
    official, tmp_path
):
    record, first, readme = official
    first["downloads"] = 1
    path = tmp_path / "official.json"
    assert metadata.preserve_official_metadata(path, record, first, readme) == first

    refreshed = copy.deepcopy(first)
    refreshed["downloads"] = 2
    assert metadata.preserve_official_metadata(path, record, refreshed, readme) == first
    assert read_json(path) == first


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", "main"),
        ("license", "unknown"),
        ("language", "en"),
        ("weights_sha256", "invalid"),
        ("evaluation_independence", True),
        ("fleurs_training_declared", True),
    ],
)
def test_candidate_config_fail_closed(alt_root, field, value):
    document = read_json(alt_root / metadata.CONFIG)
    document["models"]["pashto-ghag"][field] = value
    (alt_root / metadata.CONFIG).write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(VoiceError):
        metadata.candidates(alt_root)


@pytest.mark.parametrize(
    "mutation", ["pin", "license", "base", "training", "pickle", "weights", "card"]
)
def test_official_drift_rejected(official, mutation):
    record, meta, readme = official
    if mutation == "pin":
        meta["sha"] = "main"
    elif mutation == "license":
        meta["cardData"]["license"] = "mit"
    elif mutation == "base":
        meta["cardData"]["base_model"] = "different"
    elif mutation == "training":
        meta["cardData"]["datasets"] = ["google/fleurs"]
    elif mutation == "pickle":
        meta["siblings"][0]["rfilename"] = "pytorch_model.bin"
    elif mutation == "weights":
        meta["siblings"][0]["lfs"]["sha256"] = "0" * 64
    else:
        readme += b" FLEURS"
    with pytest.raises(VoiceError):
        metadata.validate_official(record, meta, readme)


@pytest.fixture
def specialist_backend(monkeypatch):
    torch = pytest.importorskip("torch")
    state = SimpleNamespace(loads=[], generates=[], feature=None)

    class Batch(dict):
        def to(self, device):
            assert device == "cpu"
            return self

    class Processor:
        def __init__(self, *args):
            pass

        @classmethod
        def from_pretrained(cls, repository, **options):
            state.loads.append(("processor", repository, options))
            return cls()

        def __call__(self, samples, **options):
            assert len(samples) == 1600
            assert options["sampling_rate"] == 16000
            return Batch(input_features=torch.ones((1, 80, 10)))

        def batch_decode(self, ids, **options):
            return ["synthetic decoder text"]

    class Tokenizer:
        @staticmethod
        def from_pretrained(repository, **options):
            state.loads.append(("tokenizer", repository, options))
            return object()

    class Feature:
        def __init__(self, **options):
            state.feature = options

    class Model:
        config = SimpleNamespace(eos_token_id=2)

        @classmethod
        def from_pretrained(cls, repository, **options):
            state.loads.append(("model", repository, options))
            return cls()

        def to(self, device):
            assert device == "cpu"
            return self

        def eval(self):
            return self

        def requires_grad_(self, value):
            assert value is False
            return self

        def generate(self, **options):
            state.generates.append(options)
            return torch.tensor([[1, 2]])

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoProcessor=Processor,
            AutoTokenizer=Tokenizer,
            WhisperProcessor=Processor,
            WhisperFeatureExtractor=Feature,
            WhisperForConditionalGeneration=Model,
        ),
    )
    return state


@pytest.mark.parametrize("key,language", [("pashto-ghag", "ps"), ("buzzasr-sindhi", "sd")])
def test_specialist_safe_load_same_frozen_greedy_decode(
    alt_root, specialist_backend, wav_bytes, key, language
):
    candidate = metadata.candidates(alt_root)[key]
    if key == "pashto-ghag":
        put_json(
            metadata.snapshot(alt_root, candidate) / "processor_config.json",
            {
                "processor_class": "WhisperProcessor",
                "feature_extractor": {
                    "feature_extractor_type": "WhisperFeatureExtractor",
                    "feature_size": 80,
                    "sampling_rate": 16000,
                    "dither": 0,
                },
            },
        )
    adapter = SpecialistWhisperAdapter(alt_root, key)
    service = TranscriptionService(adapter)
    first = service.transcribe(wav_bytes, language)
    second = service.transcribe(wav_bytes, language)
    assert first.transcript.checksum == second.transcript.checksum
    assert len(specialist_backend.loads) == 2
    for kind, repository, options in specialist_backend.loads:
        assert repository == candidate["repository"]
        assert options["revision"] == candidate["revision"]
        assert options["local_files_only"] is True
        assert options["trust_remote_code"] is False
        assert options["token"] is False
        if kind == "model":
            assert options["use_safetensors"] is True
            assert str(options["dtype"]) == "torch.float32"
    assert specialist_backend.generates[0]["language"] == language
    assert specialist_backend.generates[0]["num_beams"] == 1
    assert specialist_backend.generates[0]["max_new_tokens"] == 256
    assert specialist_backend.generates[0]["do_sample"] is False
    with pytest.raises(VoiceError, match="unsupported_language"):
        service.transcribe(wav_bytes, "en")


def test_processor_layout_invalid_no_fallback(alt_root, specialist_backend):
    record = metadata.candidates(alt_root)["pashto-ghag"]
    put_json(
        metadata.snapshot(alt_root, record) / "processor_config.json",
        {
            "processor_class": "RemoteCode",
            "feature_extractor": {},
        },
    )
    with pytest.raises(VoiceError, match="invalid_config"):
        SpecialistWhisperAdapter(alt_root, "pashto-ghag")._load()
    assert specialist_backend.loads == []


@pytest.fixture
def human_input(tmp_path, wav_file):
    # Synthetic tests ONLY; these attestations are intentionally not genuine research data.
    checksum = hashlib.sha256(wav_file.read_bytes()).hexdigest()
    record = {
        "recording_id": "test_001",
        "speaker_pseudonym": "test_speaker",
        "audio_path": wav_file.name,
        "audio_sha256": checksum,
        "original_audio_sha256": checksum,
        "reference_text": "سنڌي",
        "reference_author": "test_author",
        "reference_provenance": "synthetic test only",
        "recorded_at": "2026-09-13T12:00:00Z",
        "consent_confirmed": True,
        "use_permission_confirmed": True,
        "language": "sd",
        "source": "human_recording",
        "fresh_human_recording_confirmed": True,
        "not_used_for_model_training_confirmed": True,
    }
    return {"schema_version": holdout.VERSION, "excluded_speaker_ids": [], "samples": [record]}


@pytest.mark.parametrize(
    "field,value",
    [
        ("recording_id", "../bad"),
        ("speaker_pseudonym", "person@example.com"),
        ("audio_path", "../outside.wav"),
        ("audio_sha256", "0" * 64),
        ("original_audio_sha256", "0" * 64),
        ("reference_text", "   "),
        ("reference_text", "..."),
        ("reference_text", "\ud800"),
        ("reference_author", ""),
        ("reference_provenance", None),
        ("recorded_at", "2026-09-13"),
        ("consent_confirmed", False),
        ("use_permission_confirmed", 1),
        ("language", "ur"),
        ("source", "tts"),
        ("fresh_human_recording_confirmed", False),
        ("not_used_for_model_training_confirmed", False),
    ],
)
def test_holdout_rejects_invalid_or_unconsented_data(human_input, tmp_path, field, value):
    human_input["samples"][0][field] = value
    with pytest.raises(VoiceError):
        holdout.validate(human_input, tmp_path)


def test_holdout_dedup_and_speaker_leakage(human_input, tmp_path):
    human_input["samples"].append(copy.deepcopy(human_input["samples"][0]))
    with pytest.raises(VoiceError):
        holdout.validate(human_input, tmp_path)
    human_input["samples"][1]["recording_id"] = "other"
    with pytest.raises(VoiceError):
        holdout.validate(human_input, tmp_path)
    human_input["samples"].pop()
    human_input["excluded_speaker_ids"] = ["test_speaker"]
    with pytest.raises(VoiceError):
        holdout.validate(human_input, tmp_path)


def test_holdout_forbids_inferred_or_retrieval_fields(human_input, tmp_path):
    human_input["samples"][0]["predicted_reference"] = "not human"
    with pytest.raises(VoiceError):
        holdout.validate(human_input, tmp_path)


def test_empty_holdout_pending_cannot_freeze(tmp_path):
    document = {"schema_version": holdout.VERSION, "samples": [], "excluded_speaker_ids": []}
    assert holdout.validate(document, tmp_path)["samples"] == []
    source = tmp_path / "input.json"
    put_json(source, document)
    with pytest.raises(VoiceError):
        holdout.freeze(source, tmp_path, tmp_path / "output", tmp_path / "registry.json")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("tamper", ["audio", "manifest", "registry", "extra"])
def test_holdout_freeze_verify_determinism_and_tamper(human_input, tmp_path, tamper):
    source, output, registry = (
        tmp_path / "input.json",
        tmp_path / "output",
        tmp_path / "registry.json",
    )
    put_json(source, human_input)
    first = holdout.freeze(source, tmp_path, output, registry)
    files = {
        p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob("*") if p.is_file()
    }
    assert first == holdout.freeze(source, tmp_path, output, registry)
    assert files == {
        p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob("*") if p.is_file()
    }
    if tamper == "audio":
        path = output / "audio/test_001.wav"
        path.write_bytes(path.read_bytes()[:-1] + b"\x01")
    elif tamper == "manifest":
        path = output / "manifest.json"
        document = read_json(path)
        document["sample_count"] = 2
        path.write_text(json.dumps(document), encoding="utf-8")
    elif tamper == "registry":
        registry.write_text("{}\n", encoding="utf-8")
    else:
        (output / "unexpected.txt").write_text("bad", encoding="utf-8")
    with pytest.raises(VoiceError):
        holdout.verify(output, registry)


def test_freeze_refuses_source_drift(human_input, tmp_path):
    source, output, registry = (
        tmp_path / "input.json",
        tmp_path / "output",
        tmp_path / "registry.json",
    )
    put_json(source, human_input)
    holdout.freeze(source, tmp_path, output, registry)
    human_input["samples"][0]["reference_text"] += " بدل"
    source.write_text(json.dumps(human_input), encoding="utf-8")
    with pytest.raises(VoiceError):
        holdout.freeze(source, tmp_path, output, registry)


def test_holdout_preserves_human_unicode_reference(human_input, tmp_path):
    human_input["samples"][0]["reference_text"] = "  سنڌي\n  ٻولي  "
    assert (
        holdout.validate(human_input, tmp_path)["samples"][0]["reference_text"]
        == "  سنڌي\n  ٻولي  "
    )


def test_pashto_summary_frozen_micro_failures_unclamped():
    records = [
        {
            "language": "ps",
            "status": "SUCCESS",
            "scoring": score("one", "one two three"),
            "timing": {"stt_ms": 100},
            "audio_duration_seconds": 2,
        },
        {"language": "ps", "status": "FAILED", "scoring": score("two", ""), "timing": None},
    ]
    result = runner.summarize_pashto(records)
    assert result["wer"] == 1.5
    assert result["failed_samples"] == 1
    assert result["timed_calls"] == 1
    assert result["real_time_factor"]["mean"] == 0.05
    assert "overall" not in result


def test_semantic_checksum_excludes_observations():
    records = [{"sample_id": "synthetic", "transcript": "same", "timing": {"stt_ms": 1}}]

    def semantic():
        return record_checksum([{k: v for k, v in r.items() if k != "timing"} for r in records])

    first = semantic()
    records[0]["timing"]["stt_ms"] = 999
    assert semantic() == first


def test_no_candidate_execution_without_preregistration(alt_root):
    with pytest.raises((VoiceError, FileNotFoundError)):
        runner.execute(alt_root)
    assert not (alt_root / metadata.OUTPUT / "execution.started.json").exists()


def test_historical_drift_aborts_before_candidate(alt_root, monkeypatch):
    monkeypatch.setattr(runner, "verified_input", lambda _: ({}, SimpleNamespace(samples=[])))
    monkeypatch.setattr(runner, "file_sha256", lambda _: "0" * 64)
    with pytest.raises(VoiceError, match="checksum_mismatch"):
        runner.prerequisites(alt_root)


def test_synthetic_runner_exact_one_scored_attempt_no_retry(alt_root, monkeypatch, wav_bytes):
    bundle = alt_root / runner.ARTIFACT_PATH
    bundle.mkdir(parents=True)
    (bundle / "test.wav").write_bytes(wav_bytes)
    sample = EvaluationSample(
        "test_ps",
        Language.PASHTO,
        "test.wav",
        hashlib.sha256(wav_bytes).hexdigest(),
        "synthetic test",
        "test_author",
        "human_recording",
    )
    registration = {"dataset": {"manifest_sha256": "synthetic-only"}}
    monkeypatch.setattr(runner, "verify_registration", lambda _: registration)
    monkeypatch.setattr(runner, "prerequisites", lambda _: ({}, [sample]))
    monkeypatch.setattr(runner, "verified_assets", lambda *_: {"synthetic": True})
    monkeypatch.setattr(runner, "environment", lambda: {"device": "cpu"})
    calls = []

    class Adapter(SpecialistWhisperAdapter):
        def _load(self):
            pass

        def transcribe(self, audio, language):
            calls.append(language)
            raise VoiceError(ErrorCode.INFERENCE_FAILED)

    monkeypatch.setattr(runner, "SpecialistWhisperAdapter", Adapter)
    (alt_root / metadata.OUTPUT).mkdir(parents=True)
    result = runner.execute(alt_root)
    assert calls == [Language.PASHTO, Language.PASHTO]  # one warmup, one scored call
    assert result["summary"]["failed_samples"] == 1
    assert result["summary"]["wer"] == 1
    assert result["records"][0]["transcript"] is None
    assert result["evaluation_independence"] is False
    with pytest.raises(FileExistsError):
        runner.execute(alt_root)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "tamper", ["text", "audio", "score", "independence", "timing", "field", "model"]
)
def test_sample_evidence_verification_and_tamper(alt_root, wav_bytes, tamper):
    from sahulat_voice.transcript import build_transcript

    bundle = alt_root / runner.ARTIFACT_PATH
    bundle.mkdir(parents=True)
    (bundle / "test.wav").write_bytes(wav_bytes)
    sample = EvaluationSample(
        "test_ps",
        Language.PASHTO,
        "test.wav",
        hashlib.sha256(wav_bytes).hexdigest(),
        "synthetic test",
        "test_author",
        "human_recording",
    )
    candidate = metadata.candidates(alt_root)["pashto-ghag"]
    model = metadata.spec(candidate)
    transcript = build_transcript(
        sample.audio_sha256, sample.language, model, "synthetic test"
    ).record()
    record = {
        "schema_version": "voice-scored-sample-v1",
        "sample_id": sample.sample_id,
        "language": "ps",
        "audio_sha256": sample.audio_sha256,
        "audio_duration_seconds": 0.1,
        "model": runner.model_identity_key(model),
        "status": "SUCCESS",
        "failure_code": None,
        "failure_stage": None,
        "raw_decoder_output": "synthetic test",
        "raw_decoder_codepoints_if_invalid_utf8": None,
        "transcript": transcript,
        "scoring": score(sample.reference_text, "synthetic test"),
        "timing": {
            "stt_ms": 1,
            "audio_validation_ms": 1,
            "total_ms": 2,
            "adapter_base_model_load_ms_lifetime": 5,
        },
        **{key: candidate[key] for key in ("evaluation_independence", "reason", "evidence_class")},
    }
    runner.verify_sample(alt_root, sample, record, tagged=True)
    if tamper == "text":
        record["raw_decoder_output"] = "changed"
    elif tamper == "audio":
        record["audio_duration_seconds"] = 5
    elif tamper == "score":
        record["scoring"]["wer"] = 1
    elif tamper == "independence":
        record["evaluation_independence"] = True
    elif tamper == "timing":
        record["timing"]["stt_ms"] = -1
    elif tamper == "field":
        record["reranking_score"] = 1
    else:
        record["model"]["revision"] = "main"
    with pytest.raises(VoiceError):
        runner.verify_sample(alt_root, sample, record, tagged=True)


@pytest.mark.parametrize("target", ["schema", "audio_format", "missing_metadata"])
def test_holdout_schema_and_audio_validation(human_input, tmp_path, target):
    if target == "schema":
        human_input["schema_version"] = "sindhi-holdout-input-v2"
    elif target == "missing_metadata":
        del human_input["samples"][0]["reference_author"]
    else:
        (tmp_path / human_input["samples"][0]["audio_path"]).write_bytes(b"not audio")
    with pytest.raises(VoiceError):
        holdout.validate(human_input, tmp_path)


@pytest.mark.model
def test_pashto_cached_warmup_and_completed_frozen_evidence():
    if os.environ.get("RUN_VOICE_ALT_EVIDENCE_TESTS") != "1":
        pytest.skip("Opt-in validates recorded candidate inference; never reruns historical models")
    evidence = runner.verify(ROOT)
    result = read_json(ROOT / metadata.OUTPUT / "pashto-ghag.json")
    assert evidence["historical_files_unchanged"] is True
    assert evidence["pashto"]["sample_count"] == 50
    assert result["unscored_warmup"]["status"] == "SUCCESS"
    assert result["unscored_warmup"]["transcript"]["text"]
    assert result["environment"]["device"] == "cpu"
    assert result["inference_retries"] == 0
