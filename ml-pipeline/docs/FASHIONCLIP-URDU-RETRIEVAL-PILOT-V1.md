# FASHIONCLIP-URDU-RETRIEVAL-PILOT-V1

This is an isolated, local-only product retrieval experiment. It does not change
the frozen OpenCLIP production selection, EVAL-VISUAL-V1 artifacts, or any
production search route. Outputs must remain labeled **PILOT** and are not a
production model recommendation.

## Pinned assets and protocol

- Gallery: the verified Khaadi V1 fixture, 400 valid products and 2,093 retained
  images. The loader verifies the authoritative source, manifest, visual audit,
  and every retained image binary before use.
- FashionCLIP: `patrickjohncyh/fashion-clip` at
  `7e3ba62ce16b379a1ab479346b66f192e76f51b7`.
- Comparison baseline: `laion/CLIP-ViT-B-32-laion2B-s34B-b79K` at
  `1a25a446712ba5ee05982a381eed697ef9b435cf`.
- Each pilot model uses its own pinned checkpoint for both its image and text
  tower. Embeddings are L2-normalized; score is cosine similarity. The top five
  distinct products use MAX similarity over all retained product images.
- Both an English human-reference track and direct original-Urdu track are
  evaluated. Only the English-reference track is used to name the strongest
  existing model per language. OpenCLIP is run against the same queries and
  gallery when its local text encoder is available.
- A separately configured translation adapter is disabled by default. It must
  be a locally available sequence-to-sequence checkpoint pinned to an immutable
  revision. No lookup-table translator is used. Translation outputs are compared
  to the human English reference with case-folded surface WER/CER and retrieval
  metrics; this does not measure semantic equivalence.

## Human query and relevance workflow

Run from `ml-pipeline/`:

```powershell
python scripts/fashionclip_urdu_retrieval_pilot_v1.py init
python scripts/fashionclip_urdu_retrieval_pilot_v1.py export-products
```

Fill all 30 rows in
`data/fashionclip_urdu_retrieval_pilot_v1/queries.json`. `export-products`
creates the local Khaadi candidate list at
`artifacts/fashionclip_urdu_retrieval_pilot_v1/products_for_judging.json`.
For each query, retain the original Urdu wording and annotate:

- `language`: `ur` or `ur_en_mixed`;
- `script_profile`: `urdu_script`, `roman_urdu`, or `mixed_script`;
- `english_reference`: human-verified English counterpart;
- `translation_review` and `relevance_review`: each requires status `VERIFIED`,
  reviewer label, and ISO date;
- `relevant_product_ids`: a non-empty, duplicate-free list of product IDs from
  the verified Khaadi gallery;
- `roman_urdu_transliteration`: a separate field for Latin-script Urdu where
  applicable; never replace the original query with it;
- optional `commerce_reference`: human reference annotations only.

No generated text is marked as human-reviewed. The template intentionally has
30 empty, unreviewed slots; `validate-queries`, `freeze-queries`, and `evaluate`
reject incomplete rows. A frozen manifest binds the human annotations to the
Khaadi source checksums. Changes after freeze require a new pilot version.

```powershell
python scripts/fashionclip_urdu_retrieval_pilot_v1.py validate-queries
python scripts/fashionclip_urdu_retrieval_pilot_v1.py freeze-queries
```

## Rebuild and evaluate

Weights must already exist in the repository's local Hugging Face cache. All
model loading is offline; the command will name a missing revision/file instead
of fetching it. The indexes are pilot-only files under ignored
`artifacts/fashionclip_urdu_retrieval_pilot_v1/` and are checksum-bound to their
source/model registry. Existing pilot indexes are never silently overwritten.

```powershell
python scripts/fashionclip_urdu_retrieval_pilot_v1.py status
python scripts/fashionclip_urdu_retrieval_pilot_v1.py build-index --models fashionclip openclip
python scripts/fashionclip_urdu_retrieval_pilot_v1.py verify
python scripts/fashionclip_urdu_retrieval_pilot_v1.py evaluate --models fashionclip openclip
```

The evaluation writes query-level rankings, cosine scores, P@1, Recall@5,
nDCG@5, failed-query rate, serial latency, and false-positive/missed relevant
IDs to `evaluation_queries.json`; `evaluation.md` contains per-model/per-track
aggregates and an English-reference-only pilot winner by language. Scores are
similarities, not probabilities. Failed translation/inference calls remain
visible per query and count toward failure rate.

The Khaadi fixture has product records but this pilot has no commerce intent or
entity extractor, so intent/brand/price extraction accuracy is explicitly not
evaluated. Product relevance remains the scored commerce-facing retrieval
outcome. Speaker counts are not applicable because inputs are typed product
queries, not speech samples.

## Local demo and sample queries

```powershell
python scripts/fashionclip_urdu_retrieval_pilot_v1.py search `
  --model fashionclip `
  --urdu-query "مجھے سیاہ کڑھائی والا سوٹ دکھائیں" `
  --english-query "Show me a black embroidered suit"

python scripts/fashionclip_urdu_retrieval_pilot_v1.py serve --model fashionclip
```

The sample is illustrative only, not part of the evaluation set, and its English
wording is not claimed to be human-verified. Without an English query or enabled
translation adapter the demo embeds the original Urdu directly. The API binds to
loopback only, and exposes `POST /api/search`, `GET /api/status`, and verified
gallery thumbnails; it is not mounted into production.

Additional exploratory inputs (also not human-reviewed evaluation queries):

- Urdu script: `مجھے نیلا پرنٹڈ سوٹ دکھائیں`
- Urdu-English mixed: `مجھے black embroidered kurta دکھائیں`
- Roman Urdu: `mujhe neela printed suit dikhayen`

To test a translation adapter, separately edit
`configs/fashionclip_urdu_translation_v1.json` with an approved model ID and
40-character pinned revision that is already cached locally, then run:

```powershell
python scripts/fashionclip_urdu_retrieval_pilot_v1.py evaluate-translation
```

The adapter uses Urdu-Arabic input and English-Latin output language codes (for
compatible models such as NLLB). A model not present in the local cache is a
reported blocker.

## Current implementation gate

The local Khaadi authority and both pinned image/text checkpoints are available;
the two isolated gallery indexes are built and checksummed. Evaluation is still
**BLOCKED** because no human Urdu query translations or relevance labels have
been supplied. Therefore this implementation makes no Precision@1, Recall@5,
nDCG@5, model-winner, or production-readiness claim. No ASR, public voice corpus,
fine-tuning, or checkpoint modification is part of this pilot.

Refresh the current gate report with `python
scripts/fashionclip_urdu_retrieval_pilot_v1.py status`; it writes
`artifacts/fashionclip_urdu_retrieval_pilot_v1/pilot_status.md` and its JSON
evidence counterpart.
