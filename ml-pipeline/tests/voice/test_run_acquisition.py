import hashlib
import io
from unittest.mock import patch
from urllib.error import URLError

import pytest

from sahulat_voice.errors import VoiceError
from scripts import acquire_voice_models_v1 as acquisition


class Response(io.BytesIO):
    def __init__(self, data, content_range, status=206):
        super().__init__(data)
        self.status = status
        self.headers = {"Content-Range": content_range}


@pytest.fixture
def asset(monkeypatch):
    monkeypatch.setattr(acquisition, "BLOCK_BYTES", 4)
    return acquisition.ModelAsset("model.safetensors", hashlib.sha256(b"abcdef").hexdigest(), 6)


def test_model_limit_does_not_weaken_dataset_source_limit():
    from sahulat_voice.benchmark.source import SourceAsset

    assert acquisition.ModelAsset("model.safetensors", "a" * 64, 4 * 1024**3)
    with pytest.raises(VoiceError):
        SourceAsset("test.tar.gz", "a" * 64, 4 * 1024**3)


@pytest.mark.parametrize(
    "name,size",
    [
        ("../model.safetensors", 6),
        ("model.bin", 6),
        ("model.safetensors", 0),
        ("model.safetensors", 9 * 1024**3),
    ],
)
def test_invalid_asset_rejected(name, size):
    with pytest.raises(VoiceError):
        acquisition.ModelAsset(name, "a" * 64, size)


def test_exact_range_includes_end_in_cache_key_and_resumes(tmp_path, asset):
    with patch.object(
        acquisition, "urlopen", return_value=Response(b"abcd", "bytes 0-3/6")
    ) as call:
        path = acquisition.block("openai/whisper-large-v3", "a" * 40, asset, tmp_path, 0)
        assert path.read_bytes() == b"abcd"
        assert "voice_model_range=0-3" in call.call_args.args[0].full_url
        acquisition.block("openai/whisper-large-v3", "a" * 40, asset, tmp_path, 0)
        assert call.call_count == 1


@pytest.mark.parametrize(
    "data,content_range,status",
    [
        (b"abcd", "bytes 0-3/6", 200),
        (b"abcd", "bytes 0-3/7", 206),
        (b"abc", "bytes 0-3/6", 206),
        (b"abcd", "bytes 1-4/6", 206),
    ],
)
def test_bad_ranges_never_install(tmp_path, asset, data, content_range, status):
    with patch.object(acquisition, "urlopen", return_value=Response(data, content_range, status)):
        with pytest.raises(VoiceError):
            acquisition.block("openai/whisper-large-v3", "a" * 40, asset, tmp_path, 0)
    assert not (tmp_path / "000000.part").exists()


@pytest.mark.parametrize("data", [b"abcd", b"xxxx"])
def test_whole_model_hash_before_atomic_install(tmp_path, asset, data):
    folder, snapshot = tmp_path / "blocks", tmp_path / "snapshot"
    folder.mkdir()
    snapshot.mkdir()
    (folder / "000000.part").write_bytes(data)
    (folder / "000001.part").write_bytes(b"ef")
    if data == b"xxxx":
        with pytest.raises(VoiceError):
            acquisition.install_model(snapshot, asset, folder)
        assert not (snapshot / "model.safetensors").exists()
    else:
        path = acquisition.install_model(snapshot, asset, folder)
        assert path.read_bytes() == b"abcdef"
        assert acquisition.install_model(snapshot, asset, folder) == path
    assert not list(snapshot.glob("*.assembled"))


def test_transient_acquisition_retry_is_bounded_and_contains_no_url(tmp_path, asset, capsys):
    with patch.object(acquisition, "urlopen", side_effect=URLError("private-signed-url")) as call:
        with patch.object(acquisition.time, "sleep"):
            with pytest.raises(VoiceError, match="io_failed"):
                acquisition.block("openai/whisper-large-v3", "a" * 40, asset, tmp_path, 0)
    assert call.call_count == 5
    assert "private-signed-url" not in capsys.readouterr().out
