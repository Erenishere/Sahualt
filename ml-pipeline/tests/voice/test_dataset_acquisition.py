import hashlib
import io
from unittest.mock import patch
from urllib.error import URLError

import pytest

from sahulat_voice.benchmark.source import SourceAsset
from sahulat_voice.errors import VoiceError
from scripts import acquire_voice_dataset_v1 as acquisition


class RangeResponse(io.BytesIO):
    def __init__(self, payload, content_range, status=206):
        super().__init__(payload)
        self.status = status
        self.headers = {"Content-Range": content_range}


@pytest.fixture
def small_blocks(monkeypatch):
    # Synthetic transport bytes only: not audio, reference text or benchmark evidence.
    monkeypatch.setattr(acquisition, "BLOCK_BYTES", 4)
    return SourceAsset("data/ur_pk/audio/test.tar.gz", hashlib.sha256(b"abcdef").hexdigest(), 6)


def test_exact_range_and_fragment_reuse(tmp_path, small_blocks):
    response = RangeResponse(b"abcd", "bytes 0-3/6")
    with patch.object(acquisition, "urlopen", return_value=response) as request:
        path = acquisition.acquire_block(small_blocks, "a" * 40, tmp_path, 0)
        assert path.read_bytes() == b"abcd"
        assert request.call_args.args[0].headers["Range"] == "bytes=0-3"
        acquisition.acquire_block(small_blocks, "a" * 40, tmp_path, 0)
        assert request.call_count == 1


@pytest.mark.parametrize(
    "status,content_range,payload",
    [
        (200, "bytes 0-3/6", b"abcd"),
        (206, "bytes 1-4/6", b"abcd"),
        (206, "bytes 0-3/7", b"abcd"),
        (206, "bytes 0-3/6", b"abc"),
        (206, "bytes 0-3/6", b"abcde"),
    ],
)
def test_wrong_response_never_installed(tmp_path, small_blocks, status, content_range, payload):
    with patch.object(
        acquisition, "urlopen", return_value=RangeResponse(payload, content_range, status)
    ):
        with pytest.raises(VoiceError):
            acquisition.acquire_block(small_blocks, "a" * 40, tmp_path, 0)
    assert not (tmp_path / "000000.part").exists()


def test_bounded_retry_does_not_leak_upstream_url(tmp_path, small_blocks):
    with patch.object(acquisition, "urlopen", side_effect=URLError("secret-signed-url")) as request:
        with patch.object(acquisition.time, "sleep"):
            with pytest.raises(VoiceError, match="^io_failed$"):
                acquisition.acquire_block(small_blocks, "a" * 40, tmp_path, 0)
    assert request.call_count == acquisition.MAX_ATTEMPTS


def test_whole_checksum_assembly_and_repeat(tmp_path, small_blocks):
    blocks = tmp_path / "blocks"
    blocks.mkdir()
    (blocks / "000000.part").write_bytes(b"abcd")
    (blocks / "000001.part").write_bytes(b"ef")
    source = tmp_path / "source"
    path = acquisition.install_archive(source, small_blocks, blocks)
    assert path.read_bytes() == b"abcdef"
    assert acquisition.install_archive(source, small_blocks, blocks) == path
    assert not list(source.rglob("*.assembled"))


def test_corrupt_cached_fragment_cannot_install_archive(tmp_path, small_blocks):
    blocks = tmp_path / "blocks"
    blocks.mkdir()
    (blocks / "000000.part").write_bytes(b"xxxx")
    (blocks / "000001.part").write_bytes(b"ef")
    source = tmp_path / "source"
    with pytest.raises(VoiceError, match="checksum_mismatch"):
        acquisition.install_archive(source, small_blocks, blocks)
    assert not (source / small_blocks.path).exists()
    assert not list(source.rglob("*.assembled"))


def test_invalid_workers_fail_without_network(capsys):
    with patch.object(acquisition, "urlopen") as request:
        assert acquisition.main(["--allow-download", "--workers", "9"]) == 1
    assert not request.called
    assert "invalid_config" in capsys.readouterr().out
