import ast
import gzip
import hashlib
import io
import shutil
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from sahulat_voice.benchmark.cli import main
from sahulat_voice.benchmark.dataset import (
    _read_selected,
    freeze_subset,
    prepare_subset,
    verify_frozen,
    verify_prepared,
)
from sahulat_voice.benchmark.io import put_immutable, read_json
from sahulat_voice.benchmark.metadata import FleursRow
from sahulat_voice.benchmark.protocol import (
    ARTIFACT_PATH,
    CORPUS_PATH,
    LANGUAGE_CONFIGS,
    REGISTRY_PATH,
    preregister,
    verify_protocol,
)
from sahulat_voice.benchmark.source import SourceAsset, acquire_asset, load_source_lock
from sahulat_voice.errors import ErrorCode, VoiceError
from sahulat_voice.transcript import canonical_bytes

from .test_benchmark_audio import encoded_wav

REPOSITORY = Path(__file__).resolve().parents[2]


def descriptor(path, payload):
    return {"path": path, "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}


def archive_bytes(entries):
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name, payload in entries:
                member = tarfile.TarInfo(name)
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
    return output.getvalue()


@pytest.fixture(scope="module")
def prepared_template(tmp_path_factory):
    """Entirely synthetic source; no test record is actual FLEURS evidence."""
    root = tmp_path_factory.mktemp("synthetic_voice_benchmark")
    (root / "configs").mkdir()
    (root / "docs").mkdir()
    for relative in ["configs/eval_voice_v1.json", "docs/EVAL-VOICE-V1.md"]:
        shutil.copy2(REPOSITORY / relative, root / relative)
    shutil.copytree(REPOSITORY / "src/sahulat_voice", root / "src/sahulat_voice")
    source_root = root / ".sources"
    source_root.mkdir()
    card = b"Synthetic licensed source fixture for tests only.\n"
    (source_root / "README.md").write_bytes(card)
    source = {
        "schema_version": "fleurs-source-lock-v1",
        "repository": "google/fleurs",
        "revision": "a" * 40,
        "license": "cc-by-4.0",
        "card": descriptor("README.md", card),
        "languages": {},
    }
    for language_index, (language, config) in enumerate(LANGUAGE_CONFIGS.items()):
        metadata_path = f"data/{config}/test.tsv"
        archive_path = f"data/{config}/audio/test.tar.gz"
        lines, entries = [], []
        for index in range(50):
            identity = 1000 + language_index * 100 + index
            filename = f"{identity}.wav"
            script = f"Synthetic test-only reference {identity}."
            lines.append(f"{index}\t{filename}\t{script}\t{script}\tunused\t1600\tother\n")
            entries.append((f"test/{filename}", encoded_wav([identity / 10000, -0.1])))
        metadata = "".join(lines).encode()
        audio = archive_bytes(entries)
        for relative, payload in [(metadata_path, metadata), (archive_path, audio)]:
            path = source_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        source["languages"][language] = {
            "config": config,
            "rows": 50,
            "metadata": descriptor(metadata_path, metadata),
            "archive": descriptor(archive_path, audio),
        }
    (root / "configs/fleurs_sources_v1.json").write_bytes(canonical_bytes(source))
    preregister(root)
    prepare_subset(root, source_root)
    return root


@pytest.fixture
def benchmark_root(tmp_path, prepared_template):
    root = tmp_path / "synthetic"
    shutil.copytree(prepared_template, root)
    return root


def rewrite_json(path, transform):
    record = read_json(path)
    transform(record)
    path.write_bytes(canonical_bytes(record))


def test_round_trip_balanced_200_and_idempotent(benchmark_root):
    root = benchmark_root
    first = freeze_subset(root)
    files = {
        path.relative_to(root): path.read_bytes()
        for path in (root / ARTIFACT_PATH).rglob("*")
        if path.is_file()
    }
    prepare_subset(root, root / ".sources")
    assert freeze_subset(root) == verify_frozen(root) == first
    assert first["sample_count"] == 200
    assert first["language_counts"] == {language: 50 for language in LANGUAGE_CONFIGS}
    assert all((root / path).read_bytes() == payload for path, payload in files.items())
    assert read_json(root / ARTIFACT_PATH / "evaluation-input.json")["samples"][0][
        "reference_text"
    ].startswith("Synthetic test-only")


@pytest.mark.parametrize(
    "name",
    [
        "evaluation-input.json",
        "lineage.json",
        "metadata-audit.json",
        "manifest.json",
        "source_metadata/README.md",
    ],
)
def test_tampered_bundle_detection(benchmark_root, name):
    freeze_subset(benchmark_root)
    path = benchmark_root / ARTIFACT_PATH / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(VoiceError):
        verify_frozen(benchmark_root)


def test_tampered_audio_detection(benchmark_root):
    freeze_subset(benchmark_root)
    path = next((benchmark_root / ARTIFACT_PATH / "audio").rglob("*.wav"))
    path.write_bytes(path.read_bytes()[:-1] + b"x")
    with pytest.raises(VoiceError):
        verify_frozen(benchmark_root)


@pytest.mark.parametrize(
    "key", ["sample_count", "manifest_sha256", "semantic_sha256", "protocol_id", "model_results"]
)
def test_external_descriptor_tamper(benchmark_root, key):
    freeze_subset(benchmark_root)
    rewrite_json(benchmark_root / CORPUS_PATH, lambda record: record.update({key: "tampered"}))
    with pytest.raises(VoiceError):
        verify_frozen(benchmark_root)


@pytest.mark.parametrize(
    "path",
    [
        "configs/eval_voice_v1.json",
        "configs/fleurs_sources_v1.json",
        "docs/EVAL-VOICE-V1.md",
        "src/sahulat_voice/benchmark/audio.py",
    ],
)
def test_frozen_protocol_source_and_code_drift_rejected(benchmark_root, path):
    target = benchmark_root / path
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(VoiceError):
        verify_protocol(benchmark_root)
    with pytest.raises(VoiceError):
        preregister(benchmark_root)


def test_protocol_registry_tamper(benchmark_root):
    rewrite_json(benchmark_root / REGISTRY_PATH, lambda record: record.update(status="PENDING"))
    with pytest.raises(VoiceError):
        verify_protocol(benchmark_root)


def test_source_archive_drift_blocks_prepare(benchmark_root):
    target = next((benchmark_root / ".sources/data").rglob("*.tar.gz"))
    target.write_bytes(b"tampered source")
    with pytest.raises(VoiceError):
        prepare_subset(benchmark_root, benchmark_root / ".sources")
    assert not (benchmark_root / CORPUS_PATH).exists()


def test_extra_file_cannot_freeze(benchmark_root):
    (benchmark_root / ARTIFACT_PATH / "retrieval-output.json").write_bytes(b"{}")
    with pytest.raises(VoiceError):
        freeze_subset(benchmark_root)


def test_manifest_prohibited_field_cannot_freeze(benchmark_root):
    rewrite_json(
        benchmark_root / ARTIFACT_PATH / "manifest.json",
        lambda record: record.update(retrieval_score=0.9),
    )
    with pytest.raises(VoiceError):
        freeze_subset(benchmark_root)


@pytest.mark.parametrize("kind", ["reference", "member", "field", "malformed"])
def test_lineage_revalidated_even_if_manifest_hash_updated(benchmark_root, kind):
    path = benchmark_root / ARTIFACT_PATH / "lineage.json"

    def change(record):
        if kind == "reference":
            record["samples"][0]["raw_transcription"] = "Invented reference"
        elif kind == "member":
            record["samples"][0]["archive_member"] = "other/1000.wav"
        elif kind == "field":
            record["samples"][0]["ranking"] = []
        else:
            record["samples"][0] = None

    rewrite_json(path, change)
    rewrite_json(
        benchmark_root / ARTIFACT_PATH / "manifest.json",
        lambda record: record["files"].update(
            {"lineage.json": hashlib.sha256(path.read_bytes()).hexdigest()}
        ),
    )
    with pytest.raises(VoiceError):
        verify_prepared(benchmark_root)


def test_partial_failure_never_freezes(benchmark_root):
    with patch(
        "sahulat_voice.benchmark.dataset._read_selected",
        side_effect=VoiceError(ErrorCode.INVALID_AUDIO),
    ):
        with pytest.raises(VoiceError):
            prepare_subset(benchmark_root, benchmark_root / ".sources")
    assert not (benchmark_root / CORPUS_PATH).exists()


@pytest.mark.parametrize(
    "name", ["../1.wav", "/test/1.wav", "test\\1.wav", "test/a:1.wav", "other/1.wav"]
)
def test_archive_traversal_and_wrong_member_rejected(tmp_path, name):
    archive = tmp_path / "synthetic.tar.gz"
    archive.write_bytes(archive_bytes([(name, encoded_wav([0]))]))
    row = FleursRow(1, "1.wav", "script", "script", 1600, 1)
    with pytest.raises(VoiceError):
        _read_selected(archive, [row])


def test_missing_duplicate_and_link_archive_members_rejected(tmp_path):
    row = FleursRow(1, "1.wav", "script", "script", 1600, 1)
    for entries in [[], [("test/1.wav", encoded_wav([0]))] * 2]:
        path = tmp_path / "synthetic.tar.gz"
        path.write_bytes(archive_bytes(entries))
        with pytest.raises(VoiceError):
            _read_selected(path, [row])
    path = tmp_path / "link.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("test/1.wav")
        member.type, member.linkname = tarfile.SYMTYPE, "../outside.wav"
        archive.addfile(member)
    with pytest.raises(VoiceError):
        _read_selected(path, [row])


@pytest.mark.parametrize("path", ["../x", "/x", "C:/x", "a\\x", "a//x", "a/./x"])
def test_source_asset_paths_fail_closed(path):
    with pytest.raises(VoiceError):
        SourceAsset(path, "a" * 64, 1)


def test_pinned_download_checksum_idempotency_and_cleanup(tmp_path):
    payload = b"public synthetic source"
    asset = SourceAsset("data/test.tsv", hashlib.sha256(payload).hexdigest(), len(payload))
    with patch("urllib.request.urlopen", return_value=io.BytesIO(payload)) as download:
        path = acquire_asset(tmp_path, asset, "a" * 40)
        assert path.read_bytes() == payload
        acquire_asset(tmp_path, asset, "a" * 40)
        assert download.call_count == 1
    bad = SourceAsset("data/bad.tsv", "0" * 64, len(payload))
    with patch("urllib.request.urlopen", return_value=io.BytesIO(payload)):
        with pytest.raises(VoiceError):
            acquire_asset(tmp_path, bad, "a" * 40)
    assert not (tmp_path / bad.path).exists()
    assert not list(tmp_path.rglob("*.download"))


def test_immutable_artifact_does_not_overwrite(tmp_path):
    path = tmp_path / "artifact.json"
    put_immutable(path, b"first\n")
    put_immutable(path, b"first\n")
    with pytest.raises(VoiceError):
        put_immutable(path, b"second\n")
    assert path.read_bytes() == b"first\n"


@pytest.mark.parametrize(
    "field,value",
    [("schema_version", "v2"), ("license", "unknown"), ("revision", "main"), ("languages", {})],
)
def test_unsupported_source_lock(tmp_path, field, value):
    source = read_json(REPOSITORY / "configs/fleurs_sources_v1.json")
    source[field] = value
    path = tmp_path / "source.json"
    path.write_bytes(canonical_bytes(source))
    with pytest.raises(VoiceError):
        load_source_lock(path)


def test_cli_round_trip_and_safe_failure(benchmark_root, capsys):
    arguments = ["--repository-root", str(benchmark_root)]
    assert main(arguments + ["verify-protocol"]) == 0
    assert main(arguments + ["freeze"]) == 0
    assert main(arguments + ["verify"]) == 0
    assert main(arguments + ["prepare", "--source-root", str(benchmark_root.parent)]) == 1
    output = capsys.readouterr()
    assert "FAILED" in output.err
    assert str(benchmark_root.parent) not in output.err
    assert "NOT_RUN" in output.out


def test_benchmark_has_no_model_database_or_retrieval_imports():
    prohibited = (
        "torch",
        "transformers",
        "sahulat_text",
        "sahulat_visual",
        "sahulat_database",
        "adapters",
        "service",
        "integration",
        "sahulat_api",
    )
    for path in (REPOSITORY / "src/sahulat_voice/benchmark").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            if isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
            assert not any(name.startswith(prohibited) for name in names), path.name


def test_duplicate_json_keys_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"version":1,"version":2}', encoding="utf-8")
    with pytest.raises(VoiceError):
        read_json(path)
