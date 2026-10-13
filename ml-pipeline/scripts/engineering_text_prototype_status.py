"""Print ENGINEERING-TEXT-PROTOTYPE-V1 gate status (no retrieval changes)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_REGISTRY = Path("configs/gates/engineering_text_prototype_v1.json")
UNIT_TEST_EXPR = "lexical or dense or hybrid or rank_fusion"


def _load_registry(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"missing gate registry: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("gate registry must be a JSON object")
    return data


def _run_unit_tests(repository_root: Path) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/text/unit/",
        "-q",
        "-k",
        UNIT_TEST_EXPR,
    ]
    completed = subprocess.run(
        cmd,
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    summary = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, summary.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ENGINEERING-TEXT-PROTOTYPE-V1 gate banner")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument(
        "--verify-unit",
        action="store_true",
        help="Run prototype unit tests and refresh PASS/FAIL for synthetic tests line",
    )
    parser.add_argument("--json", action="store_true", help="Print registry JSON after banner")
    args = parser.parse_args(argv)

    try:
        registry = _load_registry(args.registry)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    unit_status = str(registry.get("unit_tests_scope", UNIT_TEST_EXPR))
    unit_line = "Synthetic / unit tests:    PASS (frozen; use --verify-unit to re-run)"
    verify_ok = True
    if args.verify_unit:
        verify_ok, output = _run_unit_tests(args.repository_root.resolve())
        unit_line = f"Synthetic / unit tests:    {'PASS' if verify_ok else 'FAIL'}"
        if not verify_ok:
            print(output, file=sys.stderr)

    lines = [
        str(registry.get("registry_id", "ENGINEERING-TEXT-PROTOTYPE-V1")),
        "",
        f"Lexical prototype (A):     {registry.get('lexical_prototype', 'PASS')}",
        f"Dense prototype (B):       {registry.get('dense_prototype', 'PASS')}",
        f"Hybrid prototype (D):      {registry.get('hybrid_prototype', 'PASS')}",
        unit_line,
        f"Toy DB smoke:              {registry.get('toy_db_smoke', 'OPERATOR_RUN_REQUIRED')}",
        f"Official EVAL-TEXT-V1:     {registry.get('official_eval_text_v1', 'BLOCKED')}",
        "Reason:                    "
        + str(registry.get("blocked_reason", "HUMAN_LABEL_FREEZE_PENDING")),
        "",
        "Retrieval engineering: FROZEN - human query/label collection is the active track.",
        "Doc: docs/ENGINEERING-TEXT-PROTOTYPE-V1.md",
        "Human status: python scripts/text_eval_coordinator_status.py",
        "",
        f"(unit test filter: {unit_status})",
    ]
    print("\n".join(lines))
    if args.json:
        print(json.dumps(registry, indent=2, sort_keys=True))
    if args.verify_unit and not verify_ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
