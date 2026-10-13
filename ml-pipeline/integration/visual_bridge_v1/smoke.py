"""Manual cached-model, loopback HTTP smoke; never a retrieval benchmark."""

import argparse
import asyncio
import io
import json
import socket
from pathlib import Path

import uvicorn
from PIL import Image

from sahulat_api.app import create_app
from sahulat_api.settings import HttpSettings
from sahulat_database.migrations import load_database_config
from sahulat_visual.errors import VisualError
from sahulat_visual.index import InMemoryVectorIndex

from .bridge import VisualIntegrationBridge
from .catalogue import ReadOnlyCatalogue
from .client import VisualAIClient
from .errors import BridgeError


async def cached_smoke(
    index_path: Path,
    index_sha256: str,
    source_system: str,
    database_env: Path | None,
) -> dict[str, object]:
    settings = HttpSettings(source_system, index_path=index_path, index_sha256=index_sha256)
    index = InMemoryVectorIndex.load(index_path)
    image = io.BytesIO()
    Image.new("RGB", (32, 32), (255, 0, 0)).save(image, format="PNG")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host="127.0.0.1",
            port=port,
            workers=1,
            access_log=False,
            proxy_headers=False,
            log_level="critical",
        )
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))
    result: dict[str, object] = {
        "bridge_version": "visual-integration-bridge-v1",
        "gate": "RED",
        "evidence_type": "cached-model-internal-HTTP-smoke-not-benchmark",
        "index_sha256": index_sha256,
        "source_system": source_system,
        "index_vectors": index.count,
        "embedding_version": index.identity.embedding_version,
        "api_smoke": "NOT_VERIFIED",
        "live_canonical_resolution": "NOT_VERIFIED",
        "resolved_products": 0,
        "catalog_writes": 0,
    }
    try:
        async with asyncio.timeout(90):
            while not server.started:
                if task.done():
                    raise BridgeError("api_unavailable")
                await asyncio.sleep(0.02)
        async with VisualAIClient(
            f"http://127.0.0.1:{port}",
            source_system=source_system,
            embedding_version=index.identity.embedding_version,
        ) as api:
            await api.health()
            await api.readiness()
            ranked = await api.search(image.getvalue(), mime_type="image/png")
            if not ranked.matches:
                raise BridgeError("canonical_resolution_failure")
            result.update(api_smoke="PASSED", api_ranked_products=len(ranked.matches))
            if database_env is None:
                raise BridgeError("approved_readonly_credentials_required")
            if not database_env.is_file():
                raise BridgeError("invalid_configuration")
            catalogue = ReadOnlyCatalogue(load_database_config(database_env))
            resolved = await VisualIntegrationBridge(api, catalogue).search(
                image.getvalue(),
                mime_type="image/png",
            )
            if [
                (m.rank, m.score, m.external_product_id, m.external_image_id)
                for m in ranked.matches
            ] != [(m.rank, m.score, m.external_product_id, m.external_image_id) for m in resolved]:
                raise BridgeError("ranking_violation")
            result.update(
                gate="GREEN",
                live_canonical_resolution="VERIFIED",
                resolved_products=len(resolved),
                ranking_preserved=True,
            )
    except BridgeError as exc:
        result["blocker"] = exc.code
    except TimeoutError:
        result["blocker"] = "api_timeout"
    finally:
        server.should_exit = True
        try:
            async with asyncio.timeout(10):
                await task
        except TimeoutError:
            server.force_exit = True
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        sock.close()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Loopback-only cached visual bridge smoke")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--source-system", required=True)
    parser.add_argument("--database-env", type=Path)
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(
            cached_smoke(args.index, args.index_sha256, args.source_system, args.database_env)
        )
    except (OSError, ValueError, RuntimeError, VisualError):
        result = {"gate": "RED", "blocker": "smoke_configuration_or_service_failure"}
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result["gate"] == "GREEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
