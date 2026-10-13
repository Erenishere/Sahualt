import argparse
import asyncio
import json
from pathlib import Path

from sahulat_database.migrations import load_database_config
from sahulat_visual.errors import InvalidImageError
from sahulat_visual.images import DEFAULT_POLICY, read_bytes

from .bridge import VisualIntegrationBridge
from .catalogue import ReadOnlyCatalogue
from .client import VisualAIClient
from .errors import BridgeError


async def run(args: argparse.Namespace) -> dict[str, object]:
    try:
        # Never default to the shared administrative .env or modify it.
        if not args.database_env.is_file():
            raise BridgeError("invalid_configuration_or_image")
        config = load_database_config(dotenv_path=args.database_env)
        catalogue = ReadOnlyCatalogue(config)
        content = read_bytes(args.image, DEFAULT_POLICY)
    except BridgeError:
        raise
    except (OSError, ValueError, InvalidImageError):
        raise BridgeError("invalid_configuration_or_image") from None
    async with VisualAIClient(
        args.api_url,
        source_system=args.source_system,
        embedding_version=args.embedding_version,
        timeout_seconds=args.timeout,
    ) as client:
        await client.health()
        await client.readiness()
        products = await VisualIntegrationBridge(client, catalogue).search(
            content,
            mime_type=args.mime_type,
            top_k=args.top_k,
        )
    return {
        "bridge_version": "visual-integration-bridge-v1",
        "status": "VERIFIED",
        "resolved_products": len(products),
        "ranking_preserved": True,
        "catalog_writes": 0,
        "results": [
            {
                "rank": p.rank,
                "product_id": str(p.product.product_id),
                "matched_image_id": str(p.canonical_image_id),
                "score": p.score,
            }
            for p in products
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Adeel-only internal visual integration harness")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--source-system", required=True)
    parser.add_argument("--embedding-version", required=True)
    parser.add_argument("--database-env", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument(
        "--mime-type", choices=["image/jpeg", "image/png", "image/webp"], required=True
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(asyncio.run(run(args)), sort_keys=True, allow_nan=False))
        return 0
    except BridgeError as exc:
        print(json.dumps({"status": "FAILED", "error": exc.code}))
        return 2
    except (KeyboardInterrupt, asyncio.CancelledError):
        print(json.dumps({"status": "CANCELLED", "error": "cancelled"}))
        return 130
