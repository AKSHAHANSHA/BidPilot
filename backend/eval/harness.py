"""Evaluation harness: run the real pipeline stages over the gold set and score the output.

Design choices that keep the numbers honest:

* The harness calls the *same* domain functions the worker calls — `extract_requirements`,
  `extract_risks`, `verify_quote`, `match_requirement`, `calculate_readiness`. It does not
  re-implement any rule, so a metric here reflects the shipped behaviour.
* With the default `GoldReplayProvider`, extraction returns the annotated requirements, so the
  extraction precision/recall it reports is ~1.0 by construction — that run validates the
  *deterministic* stages (citation verification incl. rejection, matching, scoring determinism
  and range) and the harness itself, at zero API cost. Real extraction quality is measured only
  under `--live` with the OpenAI provider.
* Ground truth is the human-correct judgement, not the matcher's guess. Where the coarse
  deterministic matcher disagrees, that surfaces in the failure report rather than being hidden
  by writing the matcher's own answer into the gold file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.ai.cost import estimate_cost
from app.ai.extraction import extract_requirements, extract_risks
from app.ai.providers.base import LLMProvider, LLMResponse
from app.documents.normalize import normalize_text
from app.domain.citation import verify_quote
from app.domain.matching import EvidenceFact, RequirementFact, match_requirement
from app.domain.scoring import (
    RequirementScore,
    RiskScore,
    ScoringInput,
    calculate_readiness,
    days_until,
)
from app.models.document_page import DocumentPage

GOLD_DIR = Path(__file__).parent / "gold"
_SCHEMA_FIELDS_REQ = (
    "original_text",
    "normalized_text",
    "category",
    "obligation",
    "expected_evidence",
    "source_page",
    "source_quote",
    "confidence",
)
_SCHEMA_FIELDS_RISK = (
    "risk_type",
    "severity",
    "summary",
    "why_it_matters",
    "suggested_action",
    "source_page",
    "source_quote",
    "confidence",
)


# --------------------------------------------------------------------------------------------
# Gold-replay provider
# --------------------------------------------------------------------------------------------


class GoldReplayProvider:
    """A provider that replays a tender's annotated requirements/risks/metadata as if extracted.

    Answers by `schema_name`, once per schema, so it is safe even if extraction batches the
    pages into more than one call (a second call returns an empty batch rather than duplicating).
    Reports zero tokens: this path makes no API call and must cost nothing.
    """

    def __init__(self, tender: dict[str, Any], *, model: str = "gold-replay") -> None:
        self._tender = tender
        self.model = model
        self.provider_name = "gold-replay"
        self._answered: set[str] = set()

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str,
        temperature: float | None = None,
    ) -> LLMResponse:
        first = schema_name not in self._answered
        self._answered.add(schema_name)
        if schema_name == "requirement_batch":
            items = [{k: r[k] for k in _SCHEMA_FIELDS_REQ} for r in self._tender["requirements"]]
            content = json.dumps({"requirements": items if first else []})
        elif schema_name == "risk_batch":
            items = [{k: r[k] for k in _SCHEMA_FIELDS_RISK} for r in self._tender["risks"]]
            content = json.dumps({"risks": items if first else []})
        elif schema_name == "tender_metadata":
            content = json.dumps(
                {
                    "buyer": self._tender.get("buyer"),
                    "reference": self._tender.get("reference"),
                    "summary": self._tender.get("notes"),
                }
            )
        else:  # pragma: no cover - defensive
            raise AssertionError(f"GoldReplayProvider has no reply for {schema_name!r}")
        return LLMResponse(
            content=content,
            input_tokens=0,
            output_tokens=0,
            provider=self.provider_name,
            model=self.model,
        )


# --------------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------------


def load_company_evidence() -> list[EvidenceFact]:
    raw = json.loads((GOLD_DIR / "company.json").read_text(encoding="utf-8"))
    return [
        EvidenceFact(
            id=e["id"],
            category=e["category"],
            title=e["title"],
            tags=tuple(e.get("tags", [])),
            is_verified=e["is_verified"],
        )
        for e in raw["evidence"]
    ]


def load_tenders() -> list[dict[str, Any]]:
    files = sorted((GOLD_DIR / "tenders").glob("*.json"))
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def _pages(tender: dict[str, Any]) -> list[DocumentPage]:
    pages: list[DocumentPage] = []
    for p in tender["pages"]:
        text = p["text"]
        pages.append(
            DocumentPage(
                page_number=p["page_number"],
                text=text,
                normalized_text=normalize_text(text),
                character_count=len(text),
                quality_score=1.0,
                extraction_method="text",
            )
        )
    return pages


# --------------------------------------------------------------------------------------------
# Metric helpers
# --------------------------------------------------------------------------------------------


def _tok(text: str) -> set[str]:
    return {t for t in normalize_text(text).casefold().split() if len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


@dataclass
class Failure:
    tender: str
    kind: str
    detail: str


@dataclass
class TenderReport:
    tender_id: str
    title: str
    requirement_prf: dict[str, float]
    mandatory_recall: float
    risk_prf: dict[str, float]
    citation_validity_rate: float
    citation_accuracy: float | None
    evidence_match_accuracy: float
    score: float
    decision_label: str
    score_in_range: bool
    label_expected: bool
    deterministic: bool
    input_tokens: int
    output_tokens: int
    cost_usd: float
    failures: list[Failure] = field(default_factory=list)


# --------------------------------------------------------------------------------------------
# Per-tender evaluation
# --------------------------------------------------------------------------------------------


async def evaluate_tender(
    tender: dict[str, Any],
    evidence: list[EvidenceFact],
    provider: LLMProvider,
    *,
    now: datetime | None = None,
) -> TenderReport:
    now = now or datetime.now(tz=UTC)
    tid = tender["id"]
    pages = _pages(tender)
    page_text = {p.page_number: p.text for p in pages}
    failures: list[Failure] = []

    req_result = await extract_requirements(provider, pages)
    risk_result = await extract_risks(provider, pages)
    extracted_reqs = req_result.requirements
    extracted_risks = risk_result.risks

    # ---- Requirement precision / recall (matched on page + normalized-text overlap) ----
    gold_reqs = tender["requirements"]
    matched_gold: set[int] = set()
    req_tp = 0
    for er in extracted_reqs:
        et = _tok(er.normalized_text)
        best_i, best_s = -1, 0.0
        for i, gr in enumerate(gold_reqs):
            if i in matched_gold or gr["source_page"] != er.source_page:
                continue
            s = _jaccard(et, _tok(gr["normalized_text"]))
            if s > best_s:
                best_i, best_s = i, s
        if best_i >= 0 and best_s >= 0.4:
            matched_gold.add(best_i)
            req_tp += 1
        else:
            failures.append(
                Failure(tid, "requirement_false_positive", f"unmatched: {er.normalized_text!r}")
            )
    req_fp = len(extracted_reqs) - req_tp
    req_fn = len(gold_reqs) - len(matched_gold)
    for i, gr in enumerate(gold_reqs):
        if i not in matched_gold:
            failures.append(
                Failure(tid, "requirement_missed", f"gold not recalled: {gr['normalized_text']!r}")
            )
    req_prf = _prf(req_tp, req_fp, req_fn)

    # ---- Mandatory recall ----
    gold_mandatory = [i for i, gr in enumerate(gold_reqs) if gr["obligation"] == "mandatory"]
    mand_hit = sum(1 for i in gold_mandatory if i in matched_gold)
    mandatory_recall = round(mand_hit / len(gold_mandatory), 4) if gold_mandatory else 1.0
    if gold_mandatory and mand_hit < len(gold_mandatory):
        failures.append(
            Failure(
                tid, "mandatory_missed", f"{len(gold_mandatory) - mand_hit} mandatory not recalled"
            )
        )

    # ---- Citation verification (real verify_quote over real page text) ----
    verified_flags: list[bool] = []
    citation_correct = 0
    citation_scored = 0
    canonical_reqs: list[Any] = []
    # Align extracted requirements back to gold to read the trap flag (mock mode: 1:1 by index).
    for idx, er in enumerate(extracted_reqs):
        v = verify_quote(quote=er.source_quote, page_text=page_text.get(er.source_page, ""))
        verified_flags.append(v.verified)
        if v.verified:
            canonical_reqs.append(er)
        gr = gold_reqs[idx] if idx < len(gold_reqs) else None
        # The citation trap can only be exercised when the exact annotated quote is fed in — that
        # is the mock-replay run. A live provider produces its own (valid) quotes and never
        # reproduces the trap, so citation_accuracy is intentionally N/A there.
        if (
            gr is not None
            and "citation_should_verify" in gr
            and er.source_quote == gr["source_quote"]
        ):
            citation_scored += 1
            if v.verified == gr["citation_should_verify"]:
                citation_correct += 1
            else:
                failures.append(
                    Failure(
                        tid,
                        "citation_mismatch",
                        f"expected verify={gr['citation_should_verify']} got {v.verified} "
                        f"for {er.source_quote[:60]!r}",
                    )
                )
    canonical_risks: list[Any] = []
    for er in extracted_risks:
        v = verify_quote(quote=er.source_quote, page_text=page_text.get(er.source_page, ""))
        verified_flags.append(v.verified)
        if v.verified:
            canonical_risks.append(er)
    citation_validity_rate = (
        round(sum(verified_flags) / len(verified_flags), 4) if verified_flags else 1.0
    )
    citation_accuracy = round(citation_correct / citation_scored, 4) if citation_scored else None

    # ---- Evidence-match accuracy (matcher isolated on gold requirements) ----
    em_total = 0
    em_correct = 0
    for gr in gold_reqs:
        if "gold_match_status" not in gr:
            continue
        em_total += 1
        fact = RequirementFact(
            category=gr["category"],
            normalized_text=gr["normalized_text"],
            expected_evidence=tuple(gr.get("expected_evidence", [])),
        )
        outcome = match_requirement(fact, evidence)
        if outcome.status.value == gr["gold_match_status"]:
            em_correct += 1
        else:
            failures.append(
                Failure(
                    tid,
                    "evidence_match_mismatch",
                    f"{gr['category']}: gold={gr['gold_match_status']} got={outcome.status.value} "
                    f"({gr['normalized_text'][:50]!r})",
                )
            )
    evidence_match_accuracy = round(em_correct / em_total, 4) if em_total else 1.0

    # ---- Risk precision / recall (matched on page + risk_type) ----
    gold_risks = tender["risks"]
    matched_gr: set[int] = set()
    risk_tp = 0
    for er in extracted_risks:
        hit = -1
        for i, g in enumerate(gold_risks):
            if i in matched_gr:
                continue
            if g["source_page"] == er.source_page and g["risk_type"] == er.risk_type.value:
                hit = i
                break
        if hit >= 0:
            matched_gr.add(hit)
            risk_tp += 1
        else:
            failures.append(
                Failure(
                    tid,
                    "risk_false_positive",
                    f"unmatched risk: {er.risk_type.value} p{er.source_page}",
                )
            )
    risk_fp = len(extracted_risks) - risk_tp
    risk_fn = len(gold_risks) - len(matched_gr)
    for i, g in enumerate(gold_risks):
        if i not in matched_gr:
            failures.append(
                Failure(
                    tid,
                    "risk_missed",
                    f"gold risk not recalled: {g['risk_type']} p{g['source_page']}",
                )
            )
    risk_prf = _prf(risk_tp, risk_fp, risk_fn)

    # ---- Deterministic scoring over citation-verified findings (mirrors the worker) ----
    deadline = now + timedelta(days=tender["submission_deadline_offset_days"])
    req_scores: list[RequirementScore] = []
    for er in canonical_reqs:
        fact = RequirementFact(
            category=er.category.value,
            normalized_text=er.normalized_text,
            expected_evidence=tuple(er.expected_evidence),
        )
        status = match_requirement(fact, evidence).status.value
        req_scores.append(
            RequirementScore(
                category=er.category.value,
                obligation=er.obligation.value,
                status=status,
                expected_evidence_count=len(er.expected_evidence),
                satisfied_evidence_count=len(er.expected_evidence) if status == "met" else 0,
            )
        )
    risk_scores = [
        RiskScore(severity=r.severity.value, risk_type=r.risk_type.value) for r in canonical_risks
    ]
    scoring_input = ScoringInput(
        requirements=req_scores,
        risks=risk_scores,
        submission_deadline=deadline,
        deadline_feasibility_days=days_until(deadline, now=now),
        bid_bond_available=None,
    )
    result = calculate_readiness(scoring_input)

    # ---- Score repeatability: identical input must yield an identical result ----
    deterministic = True
    for _ in range(2):
        again = calculate_readiness(scoring_input)
        if (
            again.overall_score != result.overall_score
            or again.decision_label != result.decision_label
            or [(d.key, d.raw_score, d.weighted_score) for d in again.dimensions]
            != [(d.key, d.raw_score, d.weighted_score) for d in result.dimensions]
        ):
            deterministic = False
            break
    if not deterministic:
        failures.append(Failure(tid, "non_deterministic_score", "repeated scoring differed"))

    score = float(result.overall_score)
    label = result.decision_label.value
    in_range = tender["expected_score_min"] <= score <= tender["expected_score_max"]
    label_ok = label in tender["expected_decision_labels"]
    if not in_range:
        failures.append(
            Failure(
                tid,
                "score_out_of_range",
                f"{score} not in [{tender['expected_score_min']}, {tender['expected_score_max']}]",
            )
        )
    if not label_ok:
        failures.append(
            Failure(tid, "label_unexpected", f"{label} not in {tender['expected_decision_labels']}")
        )

    input_tokens = req_result.usage.input_tokens + risk_result.usage.input_tokens
    output_tokens = req_result.usage.output_tokens + risk_result.usage.output_tokens
    cost = (
        estimate_cost(model=provider.model, input_tokens=input_tokens, output_tokens=output_tokens)
        if input_tokens
        else 0.0
    )

    return TenderReport(
        tender_id=tid,
        title=tender["title"],
        requirement_prf=req_prf,
        mandatory_recall=mandatory_recall,
        risk_prf=risk_prf,
        citation_validity_rate=citation_validity_rate,
        citation_accuracy=citation_accuracy,
        evidence_match_accuracy=evidence_match_accuracy,
        score=round(score, 2),
        decision_label=label,
        score_in_range=in_range,
        label_expected=label_ok,
        deterministic=deterministic,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(float(cost), 6),
        failures=failures,
    )


# --------------------------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------------------------


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def aggregate(reports: list[TenderReport]) -> dict[str, Any]:
    cites = [r.citation_accuracy for r in reports if r.citation_accuracy is not None]
    return {
        "tenders": len(reports),
        "requirement_precision": _mean([r.requirement_prf["precision"] for r in reports]),
        "requirement_recall": _mean([r.requirement_prf["recall"] for r in reports]),
        "mandatory_recall": _mean([r.mandatory_recall for r in reports]),
        "risk_precision": _mean([r.risk_prf["precision"] for r in reports]),
        "risk_recall": _mean([r.risk_prf["recall"] for r in reports]),
        "citation_validity_rate": _mean([r.citation_validity_rate for r in reports]),
        "citation_accuracy": _mean(cites) if cites else None,
        "evidence_match_accuracy": _mean([r.evidence_match_accuracy for r in reports]),
        "score_in_range_rate": _mean([1.0 if r.score_in_range else 0.0 for r in reports]),
        "label_expected_rate": _mean([1.0 if r.label_expected else 0.0 for r in reports]),
        "deterministic_rate": _mean([1.0 if r.deterministic else 0.0 for r in reports]),
        "total_input_tokens": sum(r.input_tokens for r in reports),
        "total_output_tokens": sum(r.output_tokens for r in reports),
        "total_cost_usd": round(sum(r.cost_usd for r in reports), 6),
        "total_failures": sum(len(r.failures) for r in reports),
    }
