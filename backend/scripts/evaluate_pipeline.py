"""Run the gold-set evaluation and write CSV + JSON reports.

    python scripts/evaluate_pipeline.py                 # mocked (gold-replay), zero cost, default
    python scripts/evaluate_pipeline.py --live          # real OpenAI provider, cost-capped
    python scripts/evaluate_pipeline.py --live --max-cost 1.00

The default run uses `GoldReplayProvider`: no network, no API key, no cost. It validates the
deterministic stages (citation verification incl. rejection, evidence matching, scoring
determinism and score ranges) and the harness. `--live` measures real extraction quality against
the gold annotations; it refuses to run without `OPENAI_API_KEY` and aborts before spending if the
projected cost exceeds `--max-cost` (default $1.00). The live path is never invoked by the test
suite — `make test` only ever exercises the mocked run through `tests/test_evaluation.py`.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from eval.harness import (  # noqa: E402
    GoldReplayProvider,
    TenderReport,
    aggregate,
    evaluate_tender,
    load_company_evidence,
    load_tenders,
)

REPORT_DIR = BACKEND_ROOT / "eval" / "reports"

# Rough upper bound per tender for the live projection: pages are small (~3k chars) so a
# requirements + risks pass is a few thousand tokens each. Deliberately generous so the guard
# errs toward refusing rather than overspending.
_PROJECTED_TOKENS_PER_TENDER = 12_000


async def _run_mock() -> list[TenderReport]:
    evidence = load_company_evidence()
    tenders = load_tenders()
    now = datetime.now(tz=UTC)
    reports = []
    for tender in tenders:
        provider = GoldReplayProvider(tender)
        reports.append(await evaluate_tender(tender, evidence, provider, now=now))
    return reports


async def _run_live(max_cost: float) -> list[TenderReport]:
    from app.ai.cost import estimate_cost
    from app.ai.providers.openai_provider import OpenAIProvider
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_model:
        raise SystemExit(
            "--live requires OPENAI_API_KEY and OPENAI_MODEL (backend/.env). Aborting."
        )

    tenders = load_tenders()
    model = settings.openai_model
    projected = float(
        estimate_cost(
            model=model,
            input_tokens=_PROJECTED_TOKENS_PER_TENDER * len(tenders),
            output_tokens=_PROJECTED_TOKENS_PER_TENDER * len(tenders) // 2,
        )
    )
    print(f"Model: {model}. Projected upper-bound cost: ${projected:.4f}. Cap: ${max_cost:.2f}.")
    if projected > max_cost:
        raise SystemExit(
            f"Projected cost ${projected:.4f} exceeds cap ${max_cost:.2f}. Aborting before spend."
        )

    evidence = load_company_evidence()
    provider = OpenAIProvider(settings=settings)
    now = datetime.now(tz=UTC)
    reports = []
    for tender in tenders:
        print(f"  evaluating {tender['id']} against the live provider…")
        reports.append(await evaluate_tender(tender, evidence, provider, now=now))
    return reports


def _write_reports(reports: list[TenderReport], mode: str) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    summary = aggregate(reports)

    json_path = REPORT_DIR / f"evaluation_{mode}_{stamp}.json"
    json_path.write_text(
        json.dumps(
            {
                "generated_at": stamp,
                "mode": mode,
                "summary": summary,
                "tenders": [asdict(r) for r in reports],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    csv_path = REPORT_DIR / f"evaluation_{mode}_{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "tender_id",
                "req_precision",
                "req_recall",
                "mandatory_recall",
                "risk_precision",
                "risk_recall",
                "citation_validity",
                "citation_accuracy",
                "evidence_match_accuracy",
                "score",
                "decision_label",
                "score_in_range",
                "label_expected",
                "deterministic",
                "input_tokens",
                "output_tokens",
                "cost_usd",
                "failures",
            ]
        )
        for r in reports:
            writer.writerow(
                [
                    r.tender_id,
                    r.requirement_prf["precision"],
                    r.requirement_prf["recall"],
                    r.mandatory_recall,
                    r.risk_prf["precision"],
                    r.risk_prf["recall"],
                    r.citation_validity_rate,
                    "" if r.citation_accuracy is None else r.citation_accuracy,
                    r.evidence_match_accuracy,
                    r.score,
                    r.decision_label,
                    r.score_in_range,
                    r.label_expected,
                    r.deterministic,
                    r.input_tokens,
                    r.output_tokens,
                    r.cost_usd,
                    len(r.failures),
                ]
            )
        writer.writerow([])
        writer.writerow(
            ["AGGREGATE", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]
        )
        for key, value in summary.items():
            writer.writerow([key, value])
    return json_path, csv_path


def _print_summary(reports: list[TenderReport], mode: str) -> None:
    summary = aggregate(reports)
    print()
    print(f"=== Evaluation summary ({mode}) ===")
    for key, value in summary.items():
        print(f"  {key:26} {value}")
    failures = [f for r in reports for f in r.failures]
    if failures:
        print()
        print(f"--- Failure analysis ({len(failures)}) ---")
        for f in failures:
            print(f"  [{f.tender}] {f.kind}: {f.detail}")
    else:
        print("\n  No failures.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the BidPilot gold-set evaluation.")
    parser.add_argument(
        "--live", action="store_true", help="Use the real OpenAI provider (costs money)."
    )
    parser.add_argument(
        "--max-cost", type=float, default=1.00, help="Abort if projected cost exceeds this (USD)."
    )
    args = parser.parse_args()

    mode = "live" if args.live else "mock"
    reports = asyncio.run(_run_live(args.max_cost) if args.live else _run_mock())
    json_path, csv_path = _write_reports(reports, mode)
    _print_summary(reports, mode)
    print()
    print(f"  JSON: {json_path}")
    print(f"  CSV:  {csv_path}")

    summary = aggregate(reports)
    if args.live:
        print(f"\n  ACTUAL live API cost: ${summary['total_cost_usd']:.4f}")
    # Non-zero exit if any deterministic guarantee broke — those are real regressions.
    broke = summary["deterministic_rate"] < 1.0
    return 1 if broke else 0


if __name__ == "__main__":
    raise SystemExit(main())
