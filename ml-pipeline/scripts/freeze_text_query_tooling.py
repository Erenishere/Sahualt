"""Software gate freeze only; never create an empty human query dataset."""

import argparse

from sahulat_text.evaluation.protocol import load_text_protocol, verify_protocol_lock
from sahulat_text.evaluation.tooling import freeze_tooling, verify_tooling


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze/verify TEXT-QUERY-V1 tooling, not human data"
    )
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--check-working-tree", action="store_true")
    args = parser.parse_args()
    try:
        protocol = load_text_protocol()
        verify_protocol_lock(protocol)
        registry = (
            verify_tooling(protocol, check_working_tree=args.check_working_tree)
            if args.verify_only
            else freeze_tooling(protocol)
        )
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"TEXT-QUERY-V1 tooling: NOT VERIFIED; {error}")
        return 2
    print(f"TEXT-QUERY-V1 tooling: FROZEN / GREEN; snapshot={registry['snapshot_sha256']}")
    print(
        "Human data: PENDING at tooling freeze; query dataset freeze: NOT POSSIBLE; "
        "text retrieval: BLOCKED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
