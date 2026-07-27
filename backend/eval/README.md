# Gold-set evaluation

A small, honest evaluation of the BidPilot analysis pipeline against a fictional gold dataset.

## What it measures

The harness (`harness.py`) runs the **real** domain logic — requirement extraction, citation
verification, deterministic evidence matching, and deterministic scoring — over the gold tenders
and compares the output to human-authored ground truth. It does not re-implement any rule, so a
metric reflects shipped behaviour.

| Metric | Meaning |
|---|---|
| requirement precision / recall | extracted requirements vs. gold (page + text overlap) |
| mandatory recall | gold mandatory requirements recovered |
| citation validity rate | share of extracted findings whose quote verifies against the real page |
| citation accuracy | on annotated cases (incl. the deliberate trap), verified == expected |
| risk precision / recall | extracted risks vs. gold (page + type) |
| evidence-match accuracy | deterministic matcher status vs. human ground truth |
| deterministic rate | identical input → identical score, over repeated runs |
| score-in-range / label-expected | score and decision land in the calibrated band |
| cost / tokens | provider spend (zero in the mocked run) |

## Running

```bash
make eval          # mocked (gold-replay): no network, no key, zero cost — the default
make eval-live     # real OpenAI provider: cost-capped at $1.00, aborts before overspending
```

Reports are written to `eval/reports/evaluation_<mode>_<timestamp>.{json,csv}`. A committed
sample lives at `eval/reports/sample_mock_evaluation.{json,csv}`. Timestamped runs are git-ignored.

The mocked run is the one exercised by the test suite (`tests/unit/test_evaluation.py`); the live
run is never triggered by `make test`.

## The dataset

`gold/company.json` is one fictional FM company (verified evidence only counts in matching).
`gold/tenders/*.json` are five varied fictional tenders — integrated FM, IT/smart-building,
soft-FM cleaning, civil construction, and catering — spanning `do_not_bid` through `strong_bid`.
Each carries ground-truth requirement, citation (page + quote), and risk annotations, mandatory vs.
optional flags, expected evidence-match outcomes, and a calibrated score band. `t3` includes a
deliberate **citation trap**: a requirement whose quote does not appear on its cited page and must
be rejected by verification. No real or confidential tenders are used.

## Design notes

- **Gold-replay by default.** Extraction is replayed from the annotations, so requirement/risk
  recall is ~1.0 by construction — that run validates the *deterministic* stages and the harness.
  Real extraction quality is a `--live` concern.
- **Ground truth is human-correct**, not the matcher's guess. Where the coarse matcher disagrees,
  it shows up in the failure report (see `docs/08` D53) rather than being hidden.
- **Score bands are regression guards** calibrated to current deterministic output; fit quality is
  carried by `evidence_match_accuracy`.
