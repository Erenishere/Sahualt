import argparse
from pathlib import Path

from sahulat_text.documents.corpus import (
    DEFAULT_REGISTRY,
    freeze_registered_corpus,
    verify_registered_corpus,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze/verify registered corpus (no retrieval)")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    action = verify_registered_corpus if args.verify_only else freeze_registered_corpus
    registry = action(args.registry, repository_root=args.repository_root)
    print(
        f"{registry['corpus_id']}: FROZEN / VERIFIED; "
        f"records={registry['record_count']}; sha256={registry['artifact_sha256']}"
    )


if __name__ == "__main__":
    main()
