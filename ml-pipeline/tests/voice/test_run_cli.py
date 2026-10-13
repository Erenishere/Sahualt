from types import SimpleNamespace

import pytest

from sahulat_voice.benchmark.io import put_json, read_json, record_checksum
from sahulat_voice.runs import execution
from scripts import run_voice_evaluation as cli


@pytest.fixture
def cli_input(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for key in ("HF_HOME", "HF_HUB_OFFLINE", "HF_HUB_DISABLE_IMPLICIT_TOKEN"):
        monkeypatch.setenv(key, "test-only")
    descriptor = {"dataset_id": "synthetic-test-only"}
    monkeypatch.setattr(execution, "verified_input", lambda root: (descriptor, None))
    monkeypatch.setattr(
        execution, "acquired_assets", lambda root, name, check_cache: {"test": name}
    )
    results = [{"model": key, "result_sha256": key} for key in ("whisper", "mms")]
    monkeypatch.setattr(
        execution,
        "verify_model",
        lambda root, path, model: next(result for result in results if result["model"] == model),
    )
    directory = tmp_path / "artifacts/eval_voice_run_v1"
    start = {"run_version": "eval-voice-run-v1", "dataset": descriptor}
    manifest = {**start, "models": results}
    return directory, start, {**manifest, "manifest_checksum": record_checksum(manifest)}


def test_verify_roundtrip_without_new_inference(cli_input, monkeypatch):
    directory, start, manifest = cli_input
    put_json(directory / "execution.started.json", start)
    put_json(directory / "manifest.json", manifest)
    monkeypatch.setattr(
        cli.subprocess, "run", lambda *args, **kw: pytest.fail("No inference in verify")
    )
    assert cli.main(["verify"]) == 0


def test_missing_manifest_not_silently_recreated(cli_input):
    directory, start, _ = cli_input
    put_json(directory / "execution.started.json", start)
    assert cli.main(["verify"]) == 1
    assert not (directory / "manifest.json").exists()


def test_tampered_manifest_fails_closed(cli_input):
    directory, start, manifest = cli_input
    put_json(directory / "execution.started.json", start)
    put_json(directory / "manifest.json", {**manifest, "manifest_checksum": "tampered"})
    assert cli.main(["verify"]) == 1


def test_existing_checkpoint_prevents_repeat(cli_input, monkeypatch):
    directory, _, _ = cli_input
    (directory / "whisper").mkdir(parents=True)
    monkeypatch.setattr(
        cli.subprocess, "run", lambda *args, **kw: pytest.fail("No repeated inference")
    )
    assert cli.main(["run"]) == 1


def test_exclusive_start_marker_blocks_concurrent_run(cli_input, monkeypatch):
    directory, start, _ = cli_input
    put_json(directory / "execution.started.json", start)
    monkeypatch.setattr(
        cli.subprocess, "run", lambda *args, **kw: pytest.fail("No repeated inference")
    )
    assert cli.main(["run"]) == 1


def test_models_run_in_two_fresh_processes(cli_input, monkeypatch):
    directory, start, _ = cli_input
    calls = []

    def process(argv, **options):
        calls.append(argv)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", process)
    assert cli.main(["run"]) == 0
    assert len(calls) == 2
    assert calls[0][-2:] == ["--model", "whisper"]
    assert calls[1][-2:] == ["--model", "mms"]
    assert read_json(directory / "execution.started.json") == start


def test_partial_parent_execution_not_supported(cli_input):
    with pytest.raises(SystemExit):
        cli.main(["run", "--model", "whisper"])
