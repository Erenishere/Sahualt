# Text labeling V1: human input contract

This is an input schema/workflow, **not** a query set or relevance-label artifact.
Synthetic unit-test records must never be submitted or cited as benchmark evidence.
The frozen [EVAL-TEXT-V1 protocol](EVAL-TEXT-V1.md) is authoritative.

## 1. Coordinator prepares human queries

Collect at least 40 English semantic-search queries: 20 queries and 20 independent intent
groups per dev/test split, covering every configured class in each split. Authors may inspect
the frozen semantic corpus to formulate supported intents, but not retrieval results.
Do not generate/translate queries with an LLM, copy Product names as automatic labels, use
commercial filters, or infer missing product attributes. The coordinator screens scope and
declares mandatory/soft intent constraints, class, group and split before labeling/retrieval.

Store human JSON objects, one per line, in `data/eval_text_v1/human_queries.jsonl`:

| Required key | Constraint |
| --- | --- |
| `query_id` | Stable syntax `TXT-Q-0001`; exactly four digits, unique |
| `query_text` | Actual human text; nonblank, no control characters, at most 512 code points |
| `language_tag` | `en` only in V1 |
| `query_class` | One of the five classes in `configs/eval_text_v1.yaml` |
| `split` | `dev` or `test`, declared before labels and retrieval |
| `intent_group_id` | Stable syntax `TXT-I-0001`; same underlying intent/paraphrases stay in one split |
| `author_id` | Opaque alias matching `[a-z][a-z0-9_-]{1,63}`, not a name/email |
| `authorship` | Literal `human`, with genuine human process confirmation |

ID forms are syntax illustrations, not benchmark records. Every key is required; extra keys
are rejected. Preserve original query text, including meaningful punctuation/case. Duplicate
comparison normalizes/casefolds without rewriting input. The coordinator records rejected
queries/reasons and retains review notes outside the frozen query record.

```powershell
python scripts/prepare_text_evaluation.py freeze-queries --queries data/eval_text_v1/human_queries.jsonl
```

This freezes queries and their manifest. Corrections after freeze require a versioned query
dataset/protocol decision, never an overwrite informed by performance.

## 2. Two independent primary judges label every Product

For each query choose two primary judges, neither its author. The pair remains fixed across
all 400 Products for that query. Use the frozen document's Name/Description/Color evidence
only; no images, hidden source attributes, external IDs or commercial state. Judges work
independently, blinded to system identity/rankings and each other's grades.

Write `data/eval_text_v1/human_judgments.jsonl` with exactly these keys:

| Required key | Constraint |
| --- | --- |
| `query_id` | A frozen query ID |
| `product_id` | Canonical lowercase UUID from the frozen corpus, **not** Khaadi external ID |
| `judge_id` | Opaque alias, distinct from query author and other primary judge |
| `grade` | Explicit JSON integer 0, 1 or 2; no string, boolean, null or inferred default |
| `rationale` | Human semantic-evidence explanation; required/nonblank for grades 1/2 |
| `provenance` | Literal `human_manual`, truthfully attested |

Grade 2 directly matches the intent and mandatory constraints; grade 1 is a useful partial
match with supported core intent and incomplete soft preferences; grade 0 lacks relevance or
mandatory evidence. See the protocol for exact definitions. Empty rationale is permitted only
for primary grade zero. No automatically filled zeros, model-generated labels or retrieval
pools. Full minimum workload is 32,000 primary rows. Duplicate query/Product/judge rows are
rejected even when identical. Source corrections are explicit human corrections before freeze.

## 3. Third human resolves every disagreement

Write `data/eval_text_v1/human_adjudications.jsonl` for disputed pairs only:

| Required key | Constraint |
| --- | --- |
| `query_id` / `product_id` | The disputed frozen pair |
| `adjudicator_id` | Third-human opaque alias, not either primary judge |
| `grade` | Explicit final JSON integer 0/1/2, not an average |
| `rationale` | Nonblank human explanation even for final zero |
| `provenance` | Literal `human_manual` |

The query author may adjudicate but this is counted/disclosed as a bias limitation; prefer
an uninvolved reviewer. Adjudications cannot override agreed pairs. No disagreement may
remain unresolved. Genuine zero-relevance queries are retained, not assigned fake positives;
each split still requires at least one genuinely answerable query.

```powershell
python scripts/prepare_text_evaluation.py freeze-labels --judgments data/eval_text_v1/human_judgments.jsonl --adjudications data/eval_text_v1/human_adjudications.jsonl
python scripts/prepare_text_evaluation.py verify
```

Omit `--adjudications` only if the complete primary matrix contains no disagreements. Freeze
preserves individual human decisions, explicit adjudications and complete consensus qrels,
including zeros, under `artifacts/eval_text_v1/`. All files bind the corpus/protocol/query hashes;
unchanged reruns are no-ops and changed frozen inputs fail. No metrics are executed.

## 4. Human sign-off and held-out handling

The coordinator confirms genuine authorship, scope, intent grouping, judge independence and
evidence-based decisions, and controls test-label visibility until model/config choices freeze.
Validators enforce shape, explicit grades, coverage, roles, consistency and integrity; they
cannot prove human authorship, relevance truth, semantic scope or access-control compliance.
Keep reviewer alias-to-person mapping private and separate; never store credentials or PII
in canonical artifacts. Record pre-adjudication agreement and author adjudication limitations.

Current state: **no human query/judgment files supplied**. Protocol is pre-registered, but
the EVAL-TEXT-V1 dataset is not frozen and no benchmark is ready or claimed.
