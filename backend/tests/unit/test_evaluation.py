"""The gold-set evaluation, exercised through the mocked (gold-replay) harness.

These assertions guard the *deterministic* guarantees the product makes: citation verification
rejects an unsupported quote, scoring is repeatable, and each gold tender lands in its calibrated
score band. They run with no network and no API key — the live provider path is never touched by
the test suite. Real extraction quality is measured only by `make eval-live`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from eval.harness import (
    GoldReplayProvider,
    aggregate,
    evaluate_tender,
    load_company_evidence,
    load_tenders,
)


async def _run_all():
    evidence = load_company_evidence()
    tenders = load_tenders()
    now = datetime(2026, 7, 27, tzinfo=UTC)
    return [await evaluate_tender(t, evidence, GoldReplayProvider(t), now=now) for t in tenders]


async def test_gold_set_has_at_least_five_varied_tenders() -> None:
    tenders = load_tenders()
    assert len(tenders) >= 5
    # Varied: distinct titles and a spread of expected decision labels across the set.
    labels = {lbl for t in tenders for lbl in t["expected_decision_labels"]}
    assert {"do_not_bid", "weak_bid", "conditional_bid", "strong_bid"} <= labels


async def test_scoring_is_deterministic_across_the_gold_set() -> None:
    reports = await _run_all()
    assert all(r.deterministic for r in reports)
    assert aggregate(reports)["deterministic_rate"] == 1.0


async def test_replay_recovers_every_gold_requirement_and_mandatory() -> None:
    # With gold-replay extraction, recall must be perfect; this validates the plumbing and the
    # requirement/mandatory metrics themselves.
    summary = aggregate(await _run_all())
    assert summary["requirement_recall"] == 1.0
    assert summary["mandatory_recall"] == 1.0
    assert summary["risk_recall"] == 1.0


async def test_citation_trap_is_rejected() -> None:
    # t3 carries a requirement whose quote does not appear on its cited page; verification must
    # reject it, so the citation-validity rate is below 1.0 and citation accuracy stays perfect.
    reports = {r.tender_id: r for r in await _run_all()}
    t3 = reports["t3_soft_fm_cleaning"]
    assert t3.citation_validity_rate < 1.0
    assert t3.citation_accuracy == 1.0
    assert any(f.kind == "citation_mismatch" for f in t3.failures) is False


async def test_every_tender_scores_within_its_calibrated_band() -> None:
    reports = await _run_all()
    for r in reports:
        assert r.score_in_range, f"{r.tender_id} scored {r.score} outside its band"
        assert r.label_expected, f"{r.tender_id} label {r.decision_label} unexpected"


async def test_evidence_matching_accuracy_is_high() -> None:
    # The tightened deterministic matcher agrees with human ground truth on all but the known
    # residual (a specific certificate vs any certificate in the same category).
    summary = aggregate(await _run_all())
    assert summary["evidence_match_accuracy"] >= 0.9


async def test_mock_run_is_free() -> None:
    summary = aggregate(await _run_all())
    assert summary["total_cost_usd"] == 0.0
    assert summary["total_input_tokens"] == 0
