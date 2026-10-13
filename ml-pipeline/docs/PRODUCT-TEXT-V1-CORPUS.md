# PRODUCT-TEXT-V1 frozen corpus identity

Status: **FROZEN**. This registers the accepted product-text-v1 corpus, not EVAL-TEXT-V1
or any retriever. PostgreSQL remains business-data truth; the preserved JSONL is derived
research evidence.

| Property | Frozen value |
| --- | --- |
| Corpus ID | `PRODUCT-TEXT-V1` |
| Document schema | `product-text-v1` / ADR-ML-004-v1 |
| Source | Canonical PostgreSQL Product/Variant projection |
| Records | 400 |
| SHA-256 | `5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f` |
| Runtime | Python 3.12 / Unicode 15.0.0 |
| Registry | `configs/corpora/product_text_v1.json` |

The versioned registry pins JSONL bytes, manifest bytes, count and provenance. Its artifact
references use a SHA-256-addressed directory under `artifacts/corpora/product-text-v1/`.
The build workspace `artifacts/product_documents/` is **not** the immutable corpus location:
later canonical database edits can generate new working documents without changing this snapshot.

```powershell
python scripts/freeze_product_text_corpus.py
python scripts/freeze_product_text_corpus.py --verify-only
```

Registration verifies the pinned source artifact/manifest, canonical serialization, every
document checksum and manifest counts before copying either file. Repeated unchanged
registration is a no-op. Existing snapshot corruption or source drift fails rather than
overwriting/repairing evidence. Verification reads only the preserved snapshot and does not
depend on a database, current working build, external refs or human labels.

Immutability is enforced by checksum/registration policy, not claimed as operating-system
write protection. Individual files are atomically published; there is no multi-file transaction.
The registry belongs in source control. Artifact bytes follow the repository's ignored-artifact
policy and must be preserved/distributed separately with the registry for reproducibility.

Every future evaluation configuration and experiment result must reference both the corpus ID
and full SHA-256, and verify them before execution. Query and human-judgment artifacts must
receive their own independent versions/checksums; the corpus checksum does not freeze labels.
An altered corpus needs a **new corpus identity/registry**, preserving this one. A changed source
population does not by itself require product-text-v2; a changed document construction policy does.

## Next gate: EVAL-TEXT-V1 design and human judgments

Freeze the protocol before running/tuning a retriever: relevance grades, human-review/adjudication
rules, query/corpus identities, development versus held-out usage, metric definitions/denominators,
ties, missing/unjudged labels, exclusions and reporting. Do not treat unjudged products as
irrelevant or claim complete-corpus Recall from incomplete judgments without an explicit policy.

Retain proposal-plan Precision@5/@10, Recall@10, MRR and nDCG@5/@10; proposed P@1/Recall@5/HitRate
can be supplementary protocol choices, not replacements for nDCG@10. The +10% target is for
full multimodal hybrid versus lexical, not a Text V1 pass gate.

PostgreSQL FTS is the proposal-faithful lexical Baseline A. PostgreSQL now exists; BM25 is not
approved by this corpus registration. An interim BM25 choice still requires ADR-ML-002 approval
and explicit divergence rationale. FTS language/configuration/query parsing/weighting/ranking
must be frozen before evaluation, without tuning against held-out labels.

**Current boundary:** corpus FROZEN; [EVAL-TEXT-V1 protocol](EVAL-TEXT-V1.md) independently
pre-registered/checksum-locked; queries/human labels not supplied. Lexical configuration remains
pending ADR-ML-002; retrieval/embeddings/RRF/Search absent. Protocol registration does not mark
the human dataset or evaluation complete.
