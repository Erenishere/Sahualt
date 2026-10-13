"""Consent-gated first-party ASR pilot workflow; evaluation is offline and immutable."""

import argparse
import json
import os
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / ".local/voice_baseline_pilot_v1"
sys.path.insert(0, str(ROOT / "src"))

from sahulat_voice import pilot_v1 as pilot  # noqa: E402
from sahulat_voice.benchmark.io import (  # noqa: E402
    file_sha256,
    put_immutable,
    put_json,
    read_canonical_json,
    read_json,
    record_checksum,
)
from sahulat_voice.errors import VoiceError  # noqa: E402


def _input_paths(workspace: Path) -> tuple[Path, Path, Path, Path]:
    return (
        workspace / "recordings_input.json",
        workspace / "consent_registry.json",
        workspace / "audio",
        workspace / "consent-evidence",
    )


def _manifest_directory(workspace: Path, requested: Path | None) -> Path | None:
    if requested is not None:
        return requested.resolve()
    candidates = (
        [
            path
            for path in (workspace / "frozen").iterdir()
            if path.is_dir() and (path / "manifest.json").is_file()
        ]
        if (workspace / "frozen").exists()
        else []
    )
    if len(candidates) > 1:
        raise ValueError("multiple_frozen_manifests_require_explicit_selection")
    return candidates[0] if candidates else None


def _run(root: Path, workspace: Path, manifest_directory: Path) -> dict[str, object]:
    verified = pilot.verify_frozen(manifest_directory, root)
    manifest_sha = verified["manifest_sha256"]
    run_directory = workspace / "runs" / manifest_sha
    run_directory.mkdir(parents=True, exist_ok=True)
    marker = run_directory / "execution.started.json"
    private_path = run_directory / "private-results.json"
    review_path = run_directory / "error_example_reviews.json"
    report_slug = manifest_sha[:12]
    report_json = root / "reports" / f"voice_baseline_pilot_v1_comparison_{report_slug}.json"
    report_markdown = root / "reports" / f"voice_baseline_pilot_v1_comparison_{report_slug}.md"
    if (
        marker.exists()
        or private_path.exists()
        or review_path.exists()
        or report_json.exists()
        or report_markdown.exists()
    ):
        raise VoiceError(pilot.ErrorCode.INVALID_CONFIG)
    put_json(
        marker,
        {
            "protocol_id": pilot.PROTOCOL_ID,
            "manifest_sha256": manifest_sha,
            "execution_policy": "no_retry_no_resume",
        },
    )
    os.environ["HF_HOME"] = str(root / ".cache/voice/huggingface")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        import torch

        torch.set_num_threads(8)
        torch.set_num_interop_threads(8)
    except ImportError:
        pass
    results = pilot.run_evaluation(root, manifest_directory, workspace=workspace)
    put_json(private_path, results)
    put_json(review_path, pilot.error_review_template(manifest_sha))
    public_json, public_markdown = pilot.public_report(results)
    put_json(report_json, public_json)
    put_immutable(report_markdown, public_markdown.encode("utf-8"))
    registry = {
        "manifest_sha256": manifest_sha,
        "private_results_sha256": file_sha256(private_path),
        "comparison_json_sha256": file_sha256(report_json),
        "comparison_markdown_sha256": file_sha256(report_markdown),
        "comparison_json": str(report_json.relative_to(root)),
        "comparison_markdown": str(report_markdown.relative_to(root)),
    }
    put_json(run_directory / "run.registry.json", registry)
    return {
        "status": "PILOT_REPORT_WRITTEN",
        "manifest_sha256": manifest_sha,
        "model_runs": len(results["model_results"]),
        "strongest_model_by_language": results["strongest_model_by_language"],
        "comparison_markdown": registry["comparison_markdown"],
        "comparison_json": registry["comparison_json"],
        "private_results": str(private_path),
    }


def _report_path(root: Path, value: object, suffix: str) -> Path:
    relative = PurePosixPath(value) if isinstance(value, str) else PurePosixPath("/")
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() != value
        or len(relative.parts) != 2
        or relative.parts[0] != "reports"
        or not relative.name.startswith("voice_baseline_pilot_v1_comparison_")
        or relative.suffix != suffix
    ):
        raise VoiceError(pilot.ErrorCode.INVALID_MANIFEST)
    path = (root / Path(*relative.parts)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise VoiceError(pilot.ErrorCode.INVALID_MANIFEST)
    return path


def _require_run_directory(workspace: Path, run_directory: Path) -> Path:
    resolved = run_directory.resolve(strict=True)
    runs_root = (workspace / "runs").resolve()
    if resolved.parent != runs_root or not (resolved / "run.registry.json").is_file():
        raise VoiceError(pilot.ErrorCode.INVALID_CONFIG)
    return resolved


def _verify_run(root: Path, workspace: Path, run_directory: Path) -> dict[str, object]:
    run_directory = _require_run_directory(workspace, run_directory)
    registry = read_canonical_json(run_directory / "run.registry.json")
    private = read_canonical_json(run_directory / "private-results.json")
    if record_checksum(private) != registry["private_results_sha256"]:
        raise VoiceError(pilot.ErrorCode.CHECKSUM_MISMATCH)
    public_json, public_markdown = pilot.public_report(private)
    json_path = _report_path(root, registry["comparison_json"], ".json")
    md_path = _report_path(root, registry["comparison_markdown"], ".md")
    if (
        file_sha256(json_path) != registry["comparison_json_sha256"]
        or file_sha256(md_path) != registry["comparison_markdown_sha256"]
        or read_canonical_json(json_path) != public_json
        or md_path.read_text(encoding="utf-8") != public_markdown
    ):
        raise VoiceError(pilot.ErrorCode.CHECKSUM_MISMATCH)
    published = []
    for publish_directory in (run_directory / "published").glob("*"):
        publish_registry_path = publish_directory / "registry.json"
        if not publish_directory.is_dir() or not publish_registry_path.is_file():
            raise VoiceError(pilot.ErrorCode.CHECKSUM_MISMATCH)
        published_registry = read_canonical_json(publish_registry_path)
        review_document = read_canonical_json(publish_directory / "error_example_reviews.json")
        if (
            publish_directory.name != published_registry["error_review_sha256"]
            or record_checksum(review_document) != published_registry["error_review_sha256"]
        ):
            raise VoiceError(pilot.ErrorCode.CHECKSUM_MISMATCH)
        published_json, published_markdown = pilot.public_report(private, review_document)
        json_path = _report_path(root, published_registry["comparison_json"], ".json")
        md_path = _report_path(root, published_registry["comparison_markdown"], ".md")
        if (
            file_sha256(json_path) != published_registry["comparison_json_sha256"]
            or file_sha256(md_path) != published_registry["comparison_markdown_sha256"]
            or read_canonical_json(json_path) != published_json
            or md_path.read_text(encoding="utf-8") != published_markdown
        ):
            raise VoiceError(pilot.ErrorCode.CHECKSUM_MISMATCH)
        published.append(published_registry["comparison_markdown"])
    return {
        "status": "PILOT_EVIDENCE_VERIFIED",
        "manifest_sha256": registry["manifest_sha256"],
        "comparison_markdown": registry["comparison_markdown"],
        "published_example_reports": published,
    }


def _publish_examples(root: Path, workspace: Path, run_directory: Path) -> dict[str, object]:
    run_directory = _require_run_directory(workspace, run_directory)
    private = read_canonical_json(run_directory / "private-results.json")
    run_registry = read_canonical_json(run_directory / "run.registry.json")
    if record_checksum(private) != run_registry["private_results_sha256"]:
        raise VoiceError(pilot.ErrorCode.CHECKSUM_MISMATCH)
    manifest_sha = run_registry["manifest_sha256"]
    if run_directory.name != manifest_sha:
        raise VoiceError(pilot.ErrorCode.INVALID_CONFIG)
    frozen_directory = workspace / "frozen" / manifest_sha
    manifest = read_canonical_json(frozen_directory / "manifest.json")
    pilot.verify_active_consent(manifest, workspace)
    review_document = read_json(run_directory / "error_example_reviews.json")
    _, review_counts = pilot.validate_error_reviews(private, review_document)
    if review_counts["approved"] == 0:
        return {"status": "NO_APPROVED_ERROR_EXAMPLES", "review_counts": review_counts}
    public_json, public_markdown = pilot.public_report(private, review_document)
    review_sha = record_checksum(review_document)
    report_slug = f"{manifest_sha[:12]}_reviewed_{review_sha[:8]}"
    report_json = root / "reports" / f"voice_baseline_pilot_v1_comparison_{report_slug}.json"
    report_markdown = root / "reports" / f"voice_baseline_pilot_v1_comparison_{report_slug}.md"
    if report_json.exists() or report_markdown.exists():
        raise VoiceError(pilot.ErrorCode.INVALID_CONFIG)
    publish_directory = run_directory / "published" / review_sha
    put_json(publish_directory / "error_example_reviews.json", review_document)
    put_json(report_json, public_json)
    put_immutable(report_markdown, public_markdown.encode("utf-8"))
    published_registry = {
        "manifest_sha256": manifest_sha,
        "error_review_sha256": review_sha,
        "comparison_json_sha256": file_sha256(report_json),
        "comparison_markdown_sha256": file_sha256(report_markdown),
        "comparison_json": str(report_json.relative_to(root)),
        "comparison_markdown": str(report_markdown.relative_to(root)),
    }
    put_json(publish_directory / "registry.json", published_registry)
    return {
        "status": "REVIEWED_ERROR_EXAMPLES_PUBLISHED",
        "review_counts": review_counts,
        "comparison_markdown": published_registry["comparison_markdown"],
        "comparison_json": published_registry["comparison_json"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("init", "status", "validate", "freeze", "run", "publish", "verify"),
    )
    parser.add_argument("--workspace", type=Path, default=WORKSPACE)
    parser.add_argument("--manifest-dir", type=Path)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    try:
        if args.command == "init":
            print(json.dumps(pilot.initialize_workspace(ROOT, workspace), ensure_ascii=False))
        elif args.command == "status":
            print(json.dumps(pilot.status(ROOT, workspace), ensure_ascii=False, sort_keys=True))
        elif args.command == "validate":
            input_path, consent_path, audio_root, evidence_root = _input_paths(workspace)
            if not input_path.exists() or not consent_path.exists():
                pilot.initialize_workspace(ROOT, workspace)
            result = pilot.validate_bundle(
                read_json(input_path),
                read_json(consent_path),
                audio_root,
                evidence_root,
            )
            print(
                json.dumps(
                    {
                        "status": result["status"],
                        "counts": result["counts"],
                        "selection_audit_count": len(result["selection_audit"]),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        elif args.command == "freeze":
            input_path, consent_path, audio_root, evidence_root = _input_paths(workspace)
            if not input_path.exists() or not consent_path.exists():
                pilot.initialize_workspace(ROOT, workspace)
            result = pilot.freeze_bundle(
                ROOT,
                read_json(input_path),
                read_json(consent_path),
                audio_root,
                evidence_root,
                workspace,
            )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        elif args.command == "run":
            manifest_directory = _manifest_directory(workspace, args.manifest_dir)
            if manifest_directory is None:
                print(json.dumps({"status": "WAITING_FOR_RECORDINGS", "model_results": "NOT_RUN"}))
            else:
                print(
                    json.dumps(
                        _run(ROOT, workspace, manifest_directory),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
        elif args.command == "publish":
            if args.run_dir is None:
                parser.error("publish requires --run-dir")
            print(
                json.dumps(
                    _publish_examples(ROOT, workspace, args.run_dir),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            if args.run_dir is not None:
                print(json.dumps(_verify_run(ROOT, workspace, args.run_dir), ensure_ascii=False))
            else:
                manifest_directory = _manifest_directory(workspace, args.manifest_dir)
                if manifest_directory is None:
                    print(
                        json.dumps({"status": "WAITING_FOR_RECORDINGS", "model_results": "NOT_RUN"})
                    )
                else:
                    print(json.dumps(pilot.verify_frozen(manifest_directory, ROOT), sort_keys=True))
        return 0
    except VoiceError as error:
        print(json.dumps({"status": "FAILED", "error": error.code.value}))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
