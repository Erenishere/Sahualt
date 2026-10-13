# Human query authoring, import, validation and freeze

**Coordinator checklist (coverage templates, phase gates, commands):**
[EVAL-TEXT-V1-COORDINATOR-CHECKLIST.md](EVAL-TEXT-V1-COORDINATOR-CHECKLIST.md).

Tooling is available. **HUMAN QUERY DATA: PENDING. Query freeze: PENDING.** No actual human
queries have been supplied. This workflow does not create queries, replacements, relevance
labels, assignments or retrieval outputs.

Authority: [EVAL-TEXT-V1](EVAL-TEXT-V1.md), [the labeling contract](text-labeling-v1.md),
`configs/eval_text_v1.yaml` and its unchanged semantic lock. Corpus: `PRODUCT-TEXT-V1`,
400 documents, SHA-256 `5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f`.
The frozen protocol, corpus and ADR decisions are not amended by this implementation.

## 1. Humans author the exact contract

Humans create their own UTF-8 JSONL submission files outside the frozen artifact directory.
Each record has **exactly** these eight required fields, as specified by the labeling contract:

```text
query_id, query_text, language_tag, query_class, split,
intent_group_id, author_id, authorship
```

The coordinator supplies stable `TXT-Q-`/`TXT-I-` IDs with four digits, an opaque author alias,
`language_tag=en`, `authorship=human`, the class and the dev/test split. No software-assigned
IDs or inferred metadata: the frozen contract requires coordinator declaration before
labeling/retrieval. IDs are preserved, so insertion order never changes identity. No timestamps,
schema fields, product IDs, scores, ranking results or annotations may be added to a query row.
Schema/version, protocol, corpus and checksums belong in sidecar manifests instead.

The coordinator confirms genuine human authorship, semantic-only English scope, independent
intent grouping and blinding, and records rejected submissions/reasons separately. The
declarations do not prove human authorship or actual language/scope; no classifier or LLM is
introduced to guess them. Authors may inspect frozen semantic documents, never retrieval
outputs. Do not automatically copy title fields, expand queries or generate paraphrases.

## 2. Import submissions incrementally

Use Python 3.12 / Unicode 15.0.0 and the existing CLI. The source path below is the human's
actual submission, not a provided example dataset:

```powershell
python scripts/prepare_text_evaluation.py import-queries --queries path/to/human-submission.jsonl
python scripts/prepare_text_evaluation.py query-status
```

Defaults collect into `data/eval_text_v1/human_queries.jsonl` plus
`human_queries.import.json`. `--collection` selects another reviewed collection. A submission
may contain fewer than 40 queries while authors collect entries. Import still enforces every
record rule, cross-submission uniqueness and dev/test intent separation. Partial collection
is **not** validation completion, query freeze, or a GREEN human-data gate.

Existing identical records are measured no-ops across repeated registrations, not appended
duplicates. Duplicate rows within a submission, normalized duplicate text, conflicting reused
IDs and split leakage fail without altering the collection. There is no last-write-wins,
automatic correction, renumbering, class assignment or replacement suggestion.

Collection JSONL is sorted by query ID; raw human text is preserved exactly. The receipt binds
query schema, protocol/corpus identities, source-byte checksums, collection checksum and
per-record checksums. Preserve original human submission files alongside their evidence;
receipts contain hashes, not private author mappings or machine-specific paths.

Imports serialize through an exclusive local import lock. One coordinator must serialize
import, manual review and freeze operations; this is not a concurrent authoring server.
Writes are atomic **per file**, not a two-file transaction. On interruption, mismatched existing
collection/receipt pairs fail closed: restore the verified pair or explicitly review a new
collection while preserving prior evidence. An interrupted lock needs coordinator review;
do not remove another process's lock. Pre-freeze corrections require human review and retained
evidence, not silent importer overwrites. Post-freeze changes require a versioned dataset
decision consistent with the frozen protocol.

## 3. Validate the complete human collection

```powershell
python scripts/prepare_text_evaluation.py validate-queries
# Or validate a complete human file directly, without collection import:
python scripts/prepare_text_evaluation.py validate-queries --queries path/to/human-query-set.jsonl
```

Complete validation requires at least 40 English queries, at least 20 queries **and** 20
independent intent groups per split, and at least one query from each of the five configured
classes in each split. Normalized duplicates use NFKC, frozen whitespace normalization and
casefold for comparison **only**, never to rewrite human text. Nonblank text, maximum 512
code points, supported language/class/split/authorship, valid aliases/IDs, no controls or
unpaired surrogates and exact field sets are mandatory. Missing metadata is rejected, not
inferred. Errors identify source positions, missing/extra fields or concrete coverage deficits;
they do not suggest replacement query content.

Every command verifies the immutable corpus/manifest/document checksums and unchanged
pre-registered protocol lock first. Failures return nonzero and do not freeze partial input.
`query-status` succeeds as an inspection command even while human data is PENDING;
`validate-queries`, `freeze-queries` and `verify-queries` do not succeed on absent/invalid data.

## 4. Freeze and verify only a valid genuine human set

```powershell
python scripts/prepare_text_evaluation.py freeze-queries
python scripts/prepare_text_evaluation.py verify-queries
# Direct human input remains supported by the established command:
python scripts/prepare_text_evaluation.py freeze-queries --queries path/to/human-query-set.jsonl
```

Canonical artifacts remain the existing contract's `artifacts/eval_text_v1/queries.jsonl`
and `queries.manifest.json`. No new query-row format or fabricated benchmark artifact is
introduced. The sidecar adds technical `query_schema_version=text-query-input-v1`, exact
count, split/class/intent coverage, per-record hashes, normalization/runtime reference and
serialization identity to the existing manifest version/identities/checksums.

Freeze preserves all eight values; sort rows by query ID, use compact recursively sorted-key
JSON, `ensure_ascii=False`, no nonfinite numbers, strict UTF-8 and one LF per row. Per-record
SHA-256 covers the exact canonical eight-field record **without** a trailing LF. JSONL SHA-256
covers every byte including final LF. The manifest hashes its canonical payload excluding
only `manifest_checksum`, then includes that hash. No timings, timestamps, absolute paths,
random IDs, connection details or Python patch/platform differences enter frozen fingerprints.

Verification revalidates source rules, corpus/protocol/schema identities, bytes, ordering,
manifest serialization, coverage and every record hash. Rehashed but inconsistent metadata
or noncanonical ordering still fails. Unchanged repeated freezes are byte-identical no-ops,
including file modification times; drift is rejected, not repaired. Query commands never read
judgments or adjudications. Import refuses collection edits once query freeze has started.

## 5. Neutral status evidence and blinding boundary

```powershell
python scripts/prepare_text_evaluation.py query-status --status-output artifacts/eval_text_v1/text-query-v1-status.json
```

This optional deterministic evidence contains measured count/coverage, corpus/protocol
identities and a self-checksum. It omits `query_artifact_sha256` until a real query artifact
has been frozen and verified. Its filename is restricted to avoid overwriting input/policy
artifacts. No human-input file or empty frozen JSONL is created when human data is absent.

Exact eight-field validation rejects all retrieval-produced extra fields, including nested
scores/results/labels, as well as product identity/image metadata. The workflow has no
retriever/model dependencies and reads only human inputs, their receipts, registered corpus
and policy/query manifests. Query-only actions reject judgment/adjudication arguments and
bypass full-dataset readiness paths that could read judging artifacts. Automated tests guard
these dependency and data-read boundaries. Neither software nor file hashes can prove that a
human was never exposed to external retrieval results: coordinator process/sign-off remains
mandatory. No automated relevance or source-language/content inference is performed.

Judging is deferred. No Cartesian assignment files or templates are added because the frozen
contract does not require them for query authoring. Stop after query validation/freeze; do
not invoke the existing `freeze-labels` command or implement retrieval from this workflow.
