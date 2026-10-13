from collections import defaultdict
from typing import Any

import numpy as np

from ..benchmark.protocol import scoring_text
from ..contracts import Language
from ..errors import ErrorCode, VoiceError
from ..evaluation import _distance


def score(reference: str, hypothesis: str) -> dict[str, int | float]:
    # The frozen scoring view is separate from stored transcript normalization.
    expected, actual = scoring_text(reference), scoring_text(hypothesis)
    if not expected:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    words = expected.split()
    # Do not re-normalize after casefold: that would change frozen codepoint denominators.
    word_errors = _distance(words, actual.split())
    character_errors = _distance(list(expected), list(actual))
    return {
        "reference_words": len(words),
        "reference_characters": len(expected),
        "word_errors": word_errors,
        "character_errors": character_errors,
        "wer": word_errors / len(words),
        "cer": character_errors / len(expected),
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[record["language"]].append(record)
    if set(groups) != {language.value for language in Language}:
        raise VoiceError(ErrorCode.INVALID_MANIFEST)
    results: dict[str, Any] = {}
    for language, samples in sorted(groups.items()):
        totals = {
            key: sum(sample["scoring"][key] for sample in samples)
            for key in (
                "word_errors",
                "character_errors",
                "reference_words",
                "reference_characters",
            )
        }
        timings = [sample["timing"]["stt_ms"] for sample in samples if sample["timing"] is not None]
        factors = [
            sample["timing"]["stt_ms"] / (1000 * sample["audio_duration_seconds"])
            for sample in samples
            if sample["timing"] is not None
        ]
        results[language] = {
            **totals,
            "sample_count": len(samples),
            "successful_samples": sum(sample["status"] == "SUCCESS" for sample in samples),
            "failed_samples": sum(sample["status"] == "FAILED" for sample in samples),
            "timed_calls": len(timings),
            "wer": totals["word_errors"] / totals["reference_words"],
            "cer": totals["character_errors"] / totals["reference_characters"],
            "latency": {
                "population": (
                    "all_attempted_scored_calls_including_failures;excludes_warmup_and_load"
                ),
                "stt_ms": distribution(timings),
                "real_time_factor": distribution(factors),
            },
        }
    return {
        "scoring_version": "voice-asr-scoring-v1",
        "languages": results,
        "overall": {
            "aggregation": "equal-language-macro-of-per-language-micro-rates",
            "wer": sum(result["wer"] for result in results.values()) / len(results),
            "cer": sum(result["cer"] for result in results.values()) / len(results),
            "successful_samples": sum(result["successful_samples"] for result in results.values()),
            "failed_samples": sum(result["failed_samples"] for result in results.values()),
        },
    }


def distribution(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "p95": float(np.percentile(values, 95)),
    }
