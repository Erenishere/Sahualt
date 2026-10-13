import pytest

from sahulat_visual.config import Settings
from sahulat_visual.encoders.factory import create_encoder
from sahulat_visual.errors import ConfigurationError, ModelLoadError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "model,module,adapter",
    [
        ("openclip", "openclip_encoder", "OpenCLIPEncoder"),
        ("fashionclip", "fashionclip_encoder", "FashionCLIPEncoder"),
    ],
)
def test_factory_selects_once_without_heavy_downloads(monkeypatch, encoder, model, module, adapter):
    calls = []

    def construct(settings, spec):
        calls.append((settings, spec))
        return encoder

    monkeypatch.setattr(f"sahulat_visual.encoders.{module}.{adapter}", construct)
    assert create_encoder(Settings(model=model)) is encoder
    assert len(calls) == 1
    assert len(calls[0][1]["revision"]) == 40


def test_unsupported_model():
    with pytest.raises(ConfigurationError):
        Settings(model="unapproved-model")


def test_loading_failure_is_explicit(monkeypatch):
    def fail(*args):
        raise OSError("unavailable")

    monkeypatch.setattr("sahulat_visual.encoders.openclip_encoder.OpenCLIPEncoder", fail)
    with pytest.raises(ModelLoadError):
        create_encoder(Settings())


def test_environment(monkeypatch):
    monkeypatch.setenv("VISUAL_MODEL", "fashionclip")
    monkeypatch.setenv("VISUAL_BATCH_SIZE", "8")
    assert Settings.from_env().model == "fashionclip"
    assert Settings.from_env().batch_size == 8
