from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from sahulat_visual import urdu_pilot_api


def test_local_demo_returns_original_query_and_distinct_result(monkeypatch, tmp_path: Path):
    image_root = tmp_path / "data/raw/khaadi"
    image_root.mkdir(parents=True)
    (image_root / "image.jpg").write_bytes(b"fixture-image")
    authority = SimpleNamespace(
        visual_retained=(
            {
                "image_id": "folder/img-1.jpg",
                "product_id": "K-1",
                "image_path": "image.jpg",
            },
        )
    )
    index = SimpleNamespace(identity="same", count=2093)
    encoder = SimpleNamespace(identity="same")
    monkeypatch.setattr(urdu_pilot_api, "load_authority", lambda _root: authority)
    monkeypatch.setattr(urdu_pilot_api, "load_index", lambda _model, _root: index)
    monkeypatch.setattr(urdu_pilot_api, "create_encoder", lambda _model, _root: encoder)

    def search_loaded(_model, _encoder, _index, urdu, english, _root):
        return {
            "original_urdu_query": urdu,
            "english_query": english,
            "top_5": [
                {
                    "rank": 1,
                    "product_id": "K-1",
                    "matched_image_id": "folder/img-1.jpg",
                    "similarity": 0.82,
                }
            ],
        }

    monkeypatch.setattr(urdu_pilot_api, "search_with_loaded_encoder", search_loaded)
    client = TestClient(urdu_pilot_api.create_app(tmp_path))

    assert client.get("/api/status").json()["production_search_modified"] is False
    response = client.post(
        "/api/search",
        json={"urdu_query": "اصل اردو سوال", "english_query": "human reference"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["original_urdu_query"] == "اصل اردو سوال"
    assert result["english_query"] == "human reference"
    assert result["top_5"][0]["similarity"] == 0.82
    assert result["top_5"][0]["image_url"] == "/api/images/folder/img-1.jpg"
    assert client.get("/api/images/folder/img-1.jpg").status_code == 200
    assert client.get("/api/images/not-in-gallery").status_code == 404


def test_local_demo_rejects_extra_search_fields(monkeypatch, tmp_path: Path):
    authority = SimpleNamespace(visual_retained=())
    index = SimpleNamespace(identity="same", count=2093)
    encoder = SimpleNamespace(identity="same")
    monkeypatch.setattr(urdu_pilot_api, "load_authority", lambda _root: authority)
    monkeypatch.setattr(urdu_pilot_api, "load_index", lambda _model, _root: index)
    monkeypatch.setattr(urdu_pilot_api, "create_encoder", lambda _model, _root: encoder)
    monkeypatch.setattr(
        urdu_pilot_api,
        "search_with_loaded_encoder",
        lambda *_args: {"top_5": []},
    )
    client = TestClient(urdu_pilot_api.create_app(tmp_path))
    response = client.post("/api/search", json={"urdu_query": "query", "top_k": 100})
    assert response.status_code == 422
