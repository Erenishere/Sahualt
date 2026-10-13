# EVAL-TEXT-V1 protocol readiness

Protocol: **FROZEN** (`EVAL-TEXT-V1`)  
Data stage: **PENDING_HUMAN_QUERIES_AND_LABELS**  
Protocol checksum: `sha256:d6412182594f8c10b6bc950120e4997390b8ab8f5130fda441f4cfaf476175e6`  
Corpus: `PRODUCT-TEXT-V1` / `5067202e69fbe0dfd61601e23cfe037a88fcc39a533c923dbdab270e0208e43f`

- Corpus products: 400
- Frozen human queries: PENDING
- Independent judge rows: PENDING
- Minimum queries: 40; minimum independent judge rows: 32000
- Dataset ready: NO
- Evaluation executed / metrics or benchmark claims: NO

V1 is English-only, semantic text only, with dev/test intent groups disjoint. Every query/product pair needs two independent humans; unjudged is never zero. Disagreements require a third human. Labels and query text are not generated.

See docs/EVAL-TEXT-V1.md and docs/text-labeling-v1.md for the pre-registered metrics, cohort/denominator rules, schemas, human workflow and limitations. PostgreSQL FTS remains pending ADR-ML-002; no retriever, Search infrastructure, embedding, database write or Visual V1 change is implemented here.
