"""Standalone loopback-only HTTP demo for the FashionCLIP Urdu retrieval pilot."""

from pathlib import Path
from typing import Any

from .dataset import resolve_image
from .errors import VisualError
from .urdu_retrieval_pilot_v1 import (
    PILOT_VERSION,
    create_encoder,
    load_authority,
    load_index,
    repository_root,
    search_with_loaded_encoder,
)


def create_app(root: Path | None = None, model_name: str = "fashionclip") -> Any:
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import FileResponse, HTMLResponse
        from pydantic import BaseModel, ConfigDict, Field
    except ImportError as exc:
        raise RuntimeError("Install the optional API dependencies to run the local demo") from exc

    base = (root or repository_root()).resolve()
    authority = load_authority(base)
    index = load_index(model_name, base)
    encoder = create_encoder(model_name, base)
    if encoder.identity != index.identity:
        raise RuntimeError("Local checkpoint/tokenizer identity differs from the pilot index")
    image_by_id = {row["image_id"]: row for row in authority.visual_retained}
    app = FastAPI(
        title="Sahulat Urdu Fashion Retrieval Pilot",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
    )

    class SearchRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")
        urdu_query: str = Field(min_length=1, max_length=500)
        english_query: str | None = Field(default=None, max_length=500)

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return _DEMO_HTML

    @app.get("/api/status")
    def api_status() -> dict[str, Any]:
        return {
            "pilot_version": PILOT_VERSION,
            "status": "PILOT_ONLY",
            "model": model_name,
            "gallery_products": 400,
            "gallery_images": index.count,
            "production_search_modified": False,
        }

    @app.post("/api/search")
    def api_search(request: SearchRequest) -> dict[str, Any]:
        try:
            payload = search_with_loaded_encoder(
                model_name, encoder, index, request.urdu_query, request.english_query, base
            )
        except (VisualError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        for result in payload["top_5"]:
            result["image_url"] = f"/api/images/{result['matched_image_id']}"
        return payload

    @app.get("/api/images/{image_id:path}")
    def api_image(image_id: str) -> Any:
        row = image_by_id.get(image_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Image not in verified pilot gallery")
        image_path = resolve_image(base / "data/raw/khaadi", row["image_path"])
        if not image_path.is_file():
            raise HTTPException(status_code=404, detail="Verified image is unavailable")
        return FileResponse(image_path)

    return app


_DEMO_HTML = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sahulat Urdu Fashion Retrieval Pilot</title>
<style>
body{font:16px system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#202124}
h1{font-size:1.5rem}
.notice{padding:.8rem;background:#fff4d6;border:1px solid #e9cf8e;border-radius:8px}
label{display:block;margin-top:1rem;font-weight:600}
textarea,input{box-sizing:border-box;width:100%;padding:.7rem;font:inherit}
textarea{min-height:5rem;direction:rtl}
button{margin-top:1rem;padding:.7rem 1rem;font:inherit;cursor:pointer}
.results{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
gap:1rem;margin-top:1.5rem}
article{border:1px solid #ddd;border-radius:8px;overflow:hidden}
article img{width:100%;aspect-ratio:4/5;object-fit:cover}
article p{padding:0 .7rem}.muted{color:#666;font-size:.9rem}
</style>
<h1>Sahulat AI — Urdu product retrieval (pilot)</h1>
<p class="notice">Experimental local demo only. Similarity is not a relevance judgment
or a production recommendation.</p>
<label for="urdu">Original Urdu query</label>
<textarea id="urdu" lang="ur" dir="rtl" placeholder="مثال: سیاہ کڑھائی والا سوٹ دکھائیں"></textarea>
<label for="english">Optional human reference / English query</label>
<input id="english" placeholder="e.g. Show me a black embroidered suit">
<button id="search">Search local Khaadi gallery</button>
<p id="status" class="muted"></p><section id="results" class="results"></section>
<script>
document.querySelector('#search').onclick=async()=>{
 const status=document.querySelector('#status'), results=document.querySelector('#results');
 results.replaceChildren(); status.textContent='Searching…';
 try{
  const response=await fetch('/api/search',{
   method:'POST',headers:{'content-type':'application/json'},
   body:JSON.stringify({urdu_query:document.querySelector('#urdu').value,
    english_query:document.querySelector('#english').value||null})});
  const data=await response.json();
  if(!response.ok) throw new Error(data.detail||response.statusText);
  status.textContent=`${data.model} · ${data.evaluation_status} · ${data.latency_ms.toFixed(1)} ms`;
  for(const item of data.top_5){
   const card=document.createElement('article'), img=document.createElement('img'),
    p=document.createElement('p');
   img.src=item.image_url; img.alt=`Khaadi product ${item.product_id}`;
   p.textContent=`${item.rank}. ${item.product_id} · cosine ${item.similarity.toFixed(4)}`;
   card.append(img,p); results.append(card);
  }
 }catch(error){status.textContent=error.message;}
};
</script>
</html>"""
