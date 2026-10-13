# EVAL-TEXT-V1: semantic product-text evaluation protocol

Protocol status: **FROZEN / pre-registered**. Human query set and relevance judgments:
**PENDING**. No retrieval evaluation, benchmark results, or relevance labels have been
generated. The protocol freeze is not a dataset freeze or completion of Text Retrieval V1.

## Authority and corpus

The machine policy is [configs/eval_text_v1.yaml](../configs/eval_text_v1.yaml); its immutable
semantic lock is [configs/eval_text_v1.protocol.json](../configs/eval_text_v1.protocol.json).
The lock binds every policy setting and the corpus identity. Changes require a new version,
not an overwrite after observing rankings. This document and the labeling contract explain
the policy; the config/lock are the executable authority.

- Corpus: `PRODUCT-TEXT-V1`, 400 canonical Product UUIDs.
- SHA-256: `5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f`.
- Source: canonical PostgreSQL Product projection, through accepted ADR-ML-004.
- Searchable evidence: normalized Name, Description and deterministic Variant Color only.
- All documents in the frozen corpus are candidates, including fixture draft Products.
  This is research eligibility, not permission to publish incomplete commercial listings.
- Price, Currency, Availability, Stock, Size, Brand, Category, Vendor, SKU, images and external
  fixture identities are not additional relevance evidence. No attributes may be inferred.

The corpus verifier checks the registered content-addressed snapshot, manifest and document
checksums before any protocol/query/label operation. It does not query or mutate PostgreSQL.
The snapshot remains derived research data; PostgreSQL remains business truth.

## Human queries and split policy

V1 is **English-only semantic text search**. Roman Urdu, Urdu, voice, images, multimodal input
and structured commercial filters require later protocols. No multilingual claim is permitted.
Humans author at least 40 queries, with at least 20 queries and 20 independent intent groups
in each of `dev` and `test`. Each split includes at least one query from every class:

| Class | Intended coverage |
| --- | --- |
| `title_terms` | Natural terms overlapping product names |
| `attribute_focused` | Explicit semantic constraints supported by the frozen text |
| `paraphrase` | Human rephrasing, not generated or translated text |
| `contrastive` | Distinguishing similar products using documented semantic evidence |
| `sparse_description` | Intent involving products with limited descriptive evidence |

A coordinator declares query IDs, intent groups, classes and splits **before retrieval and
labeling**. Paraphrases of the same underlying intent belong to the same group; an intent
group cannot cross splits. More than 40 queries is allowed with the same rules and complete
judgment coverage. Query class and intent independence are human attestations, not inferred
by a model. Humans screen scope: a schema validator cannot decide whether natural language
secretly requests a price/stock filter.

Preserve original human query text. Duplicate detection alone uses frozen NFKC/control-
separator/whitespace normalization followed by casefold; it does not rewrite retriever input.
Exact/normalized duplicate text, blank text, control characters, unsupported fields/languages
and queries over 512 code points are rejected before freeze. Rejections must be recorded by
the coordinator, not removed later because a model performs poorly.
Duplicate normalization reuses locked `product-normalization-v1`, with Unicode 15.0.0
(Python 3.12), as verified by the registered corpus. The official protocol's
`benchmark_evidence: true` marks intended research eligibility, not existing labels/results;
synthetic test policies explicitly declare false and never become evidence.

There is no supervised training split or product split. Hyperparameters/model choices may
use `dev` only. `test` labels are coordinator-controlled and held out until decisions freeze;
no test-driven parameter selection, query editing or repeated leaderboard optimization.
File checksums are integrity checks, not access controls; the coordinator must enforce label
visibility operationally. No authentication system is implemented here.

## Relevance and human judgment process

Every query/Product pair receives two independent manual grades from the same two primary
judges for that query, using only the frozen semantic document. The query author cannot be a
primary judge. Judges must not see retriever names, scores, ranks, or each other's judgments.

| Grade | Definition |
| --- | --- |
| 2 | Directly satisfies the main intent and mandatory semantic constraints with explicit text evidence |
| 1 | Useful partial match: the core intent is supported but a soft preference is only partially satisfied |
| 0 | Irrelevant, contradicts a mandatory constraint, or lacks evidence for a mandatory semantic claim |

Do not infer an unstated attribute to make a match. The coordinator specifies the intent and
mandatory-versus-soft constraints consistently before judging, without model feedback.
Positive grades require a human rationale citing semantic evidence. Grade zero may have an
empty rationale. `human_manual` is a provenance declaration: code cannot prove authorship
or relevance truth.

Coverage is **exhaustive**, not retriever-pooled. At the minimum query count this means
16,000 pairs and **32,000 primary-judge rows**, plus adjudications. If this budget is infeasible,
revise/version the protocol before retrieval; do not silently substitute partial labels.
Unjudged pairs are errors, never implicit zeros. Duplicate judgment rows are errors, never
last-write-wins, even when their grades agree.

Agreements retain the agreed grade. Every disagreement requires an explicit third-human
adjudication and nonempty rationale, even for final grade zero; grades are never averaged.
The adjudicator cannot be either primary judge. The query author may adjudicate because a
three-person workflow otherwise becomes impossible, but author adjudication counts must be
disclosed as a bias limitation; prefer an uninvolved reviewer when available. Adjudication
cannot overwrite an agreed pair. Report raw agreement/disagreement and final-label counts.

Retain genuine zero-relevance queries in the dataset, fully judged. Never fabricate relevance
to satisfy a quota. Each split needs at least one answerable query; otherwise quality metrics
cannot support a meaningful comparison. Additional human queries require a new query freeze.

## Metrics and denominators (policy only; no metrics runner)

Primary metric: **nDCG@10**. Binary relevance means grade >= 1. For an answerable query let
`R` be the number of relevant Products across the complete 400-product corpus:

| Metric | Exact definition |
| --- | --- |
| Precision@1 / @5 / @10 | Relevant returned Products in the first K positions divided by K |
| Recall@5 / @10 | Relevant returned Products in the first K positions divided by R |
| MRR | Mean of `1 / first_relevant_rank`; zero if no relevant Product is returned; full returned ranking, at most corpus size |
| nDCG@5 / @10 | `DCG@K / IDCG@K`, gain `2^grade - 1`, discount `log2(rank + 1)`; IDCG sorts every corpus grade descending |
| HitRate@5 | 1 if any relevant Product appears in the first five positions, otherwise 0 |
| No-result rate | Fraction of all queries with an empty returned ranking |
| No-answer false-positive rate | Fraction of zero-relevance queries with any returned Product; N/A if none exist |

Unreturned positions contribute zero gain/relevance; Precision keeps denominator K even for
short rankings. Quality metrics use equal-query macro averages over answerable queries,
reported **separately for dev and test**. For zero-relevance queries Recall/nDCG/MRR/HitRate
quality is N/A for this protocol; retain their full rankings and report their separate cohort
size and diagnostic rates. Report total, answerable and zero-relevance denominators explicitly.
No combined split average or hidden exclusions may substitute for the held-out result.

No text-quality pass threshold is defined. The proposal's +10% nDCG@10 target belongs to
full multimodal hybrid versus lexical retrieval, not a Text V1 acceptance gate.

## Ranking, comparisons and timing

Rankings contain unique canonical lowercase Product UUIDs from this corpus. Order finite
scores descending; break **exact** score ties by UUID ascending. No epsilon tie buckets.
Duplicate/unknown IDs or nonfinite scores are errors. Preserve empty results and failures;
never remove unsuccessful queries from denominators.

Future comparisons use identical corpus, query set, judgments and protocol. Proposal-faithful
Baseline A is PostgreSQL FTS after ADR-ML-002; BM25 is allowed only under an explicitly
approved interim ADR and must not be renamed proposal Baseline A. Baselines B/D are later
dense text/text-only RRF, not multimodal fusion. No encoder/configuration is selected here.

For future primary-metric differences, report paired 95% percentile confidence intervals
using 10,000 intent-group cluster bootstrap resamples with seed 42. Within each split, sample
answerable intent groups with replacement, retaining all their answerable query scores for
both systems; recompute the equal-query macro difference for each resample. Use linear
quantiles for 2.5/97.5 percentiles; report query/group counts and small-sample limitations.
This is a pre-registered method, not an executed statistical result.

Future latency observations use SHA-256 of UTF-8 `42:<query_id>` ascending (query ID breaks
hash ties), one untimed warmup and five measured repeats per query, serially in a warm process
on the same otherwise-idle device. Report p50/p95 over all measured query-repeat observations
using linear quantiles; no latency pass threshold. Separately measure query preparation,
query embedding if applicable, branch retrieval, fusion if applicable and ML end-to-end.
Preparation includes validation/lexical query parsing. ML end-to-end includes all query work
but excludes HTTP/network/business enrichment, downloads, model/corpus load and index build.
Report hardware, versions, thread counts and cold setup costs separately.

## Artifact freeze and verification

See [text-labeling-v1.md](text-labeling-v1.md) for exact input schemas. The entry point is:

```powershell
python scripts/prepare_text_evaluation.py preregister
python scripts/prepare_text_evaluation.py verify
python scripts/prepare_text_evaluation.py freeze-queries --queries data/eval_text_v1/human_queries.jsonl
python scripts/prepare_text_evaluation.py freeze-labels --judgments data/eval_text_v1/human_judgments.jsonl --adjudications data/eval_text_v1/human_adjudications.jsonl
```

Only the first two commands are currently runnable without human inputs. No command generates
queries, labels, rankings or benchmark claims. Source human records are validated and serialized
without changing text or grades. Frozen outputs live in `artifacts/eval_text_v1/`: queries,
individual judgments, adjudications, complete consensus qrels and checksum-bound manifests.
Qrels contain `query_id`, canonical `product_id`, and explicit integer `grade`, including zeros.

Serialization: compact sorted-key JSON, `ensure_ascii=False`, nonfinite numbers forbidden,
UTF-8, LF after each record. Sort queries by query ID, judgments by query/Product/judge ID,
and adjudications/qrels by query/Product ID. SHA-256 binds exact artifact bytes; manifests
self-check their deterministic payload and bind corpus/protocol/query/file hashes. The
protocol fingerprint excludes the portable registry *location*, not corpus identity.
No timestamps, machine-specific paths, credentials or run IDs enter canonical fingerprints.
Immutable writes refuse changed files; per-file writes are atomic, not one multi-file filesystem
transaction. Rerunning unchanged inputs is a no-op; interruption requires rerun/verification.

Readiness distinguishes protocol frozen, queries pending/frozen, and labels pending/frozen.
Dataset readiness is never inferred from synthetic tests or an empty placeholder file.

## Limitations and stop boundary

Human query representativeness, independent judgment and relevance truth require real review.
Catalog-informed English queries on one 400-product fixture are not real-user traffic or a
multilingual/production benchmark. Pretrained model/catalog overlap may remain unknown.
Checksum integrity is not protection from an authorized person replacing artifacts.

This gate implements policy registration and human-input validation/freezing only. No metric
runner, relevance labels, retriever, Search schema, FTS, vector infrastructure, database writes,
model selection or Visual V1 changes. EVAL-TEXT-V1 results remain blocked by human data.
