"""Natural-language search over the public catalogue (`docs/09_PORTAL_SPEC.md` §5).

The division of labour is the whole design. The model reads the *query* and nothing else: it
never sees a listing, so it cannot invent one, cannot order them, and cannot be steered into
promoting one. All it produces is a `SearchInterpretation` — categories, emirates, a budget
band, keywords — which `app/ai/search.py` validates strictly and, on any failure, replaces with
a keyword derivation. Everything after that point is deterministic Python in this module.

**Why the bands renormalise.** Each signal contributes a fixed weight, but only when the query
said something about it. A query that names no emirate must not cost every listing the emirate
band; the band drops out of the blend entirely and the remaining weights carry the score, the
same treatment `app/domain/screening.py` gives an empty requirement band. Otherwise a vague
query would flatten every score towards zero and the ranking would stop meaning anything.

**Why arithmetic is exact.** Weights are integers and credits are :class:`~fractions.Fraction`,
so two listings that deserve the same score get the same score — no float epsilon deciding
which of two equal matches sorts first. Ties then break on deadline and id, so repeating a
search returns the same order.

**Why the timeliness band exists.** Without it the soonest-closing listing wins every tie, and
a tender closing tomorrow would outrank a fresh one a vendor could actually prepare a bid for.
It is deliberately the smallest band: relevance decides, urgency only separates equals.

`degraded` is not cosmetic. When no API key is configured the provider is the keyword one and
the results come from text processing; the response says so rather than letting the UI imply a
model answered.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Final

from app.ai.providers.base import LLMProvider
from app.ai.providers.keyword import KeywordProvider
from app.ai.search import interpret_query
from app.ai.structured_models import SearchInterpretation as RawInterpretation
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.enums import Emirate, TenderCategory
from app.models.listing import TenderListing
from app.repositories.listing_repository import ListingFilters, TenderListingRepository
from app.schemas.listing import label_for
from app.schemas.search import (
    MAX_REASON_LENGTH,
    MAX_REASONS,
    SearchInterpretation,
    SearchRequest,
)
from app.services.listing_service import is_open_for_applications

logger = get_logger(__name__)

#: Relative importance of each signal. Integers so the blend stays exact, and they are only
#: comparable to each other — the score is the weighted mean over the *active* bands, never a
#: sum out of 100.
CATEGORY_WEIGHT: Final = 40
EMIRATE_WEIGHT: Final = 20
KEYWORD_WEIGHT: Final = 25
BUDGET_WEIGHT: Final = 10
TIMELINESS_WEIGHT: Final = 5

#: Where a keyword hit counts for most. A term in the title is what the buyer called the work;
#: the same term buried in a 20,000-character brief is a passing mention. Per keyword only the
#: strongest field counts, so a word repeated everywhere cannot outscore two distinct matches.
_FIELD_WEIGHTS: Final[tuple[tuple[str, int], ...]] = (
    ("title", 4),
    ("tags", 3),
    ("summary", 2),
    ("description", 1),
)
_MAX_FIELD_WEIGHT: Final = max(weight for _, weight in _FIELD_WEIGHTS)

#: Days of headroom beyond which a deadline stops being a differentiator: a month is enough
#: time to prepare any bid, so 30 days and 300 days score the same.
FRESH_WINDOW_DAYS: Final = 30
#: Age at which a listing stops counting as newly published.
RECENCY_WINDOW_DAYS: Final = 60

#: Ceiling on `SearchInterpretation.budget_*` in `app/schemas/search.py`, which is narrower than
#: the AI model's own `le=1e12`. Clamped rather than allowed to fail validation: a hallucinated
#: trillion-dirham band must not turn a public search into a 500.
_MAX_BUDGET: Final = Decimal("99999999999.99")

#: Candidates fetched per requested result. Ranking a few hundred rows in Python costs
#: microseconds, and a pool the same size as the answer would mean SQL's deadline ordering —
#: not relevance — decided which listings the ranker ever saw.
_POOL_MULTIPLIER: Final = 4
_MAX_POOL: Final = 200

#: How much of a text field is scanned for keywords, following `_SCAN_LIMIT` in
#: `app/ai/providers/keyword.py`. A description may be 20,000 characters and this endpoint is
#: public, unauthenticated, and runs over the whole candidate pool: measured, the uncapped
#: version spends ~270ms normalising 200 briefs, which is a denial-of-service surface for the
#: price of a search box. The cost is that a term appearing only past this point scores nothing
#: on `description` — the lowest-weighted field of the four.
_MAX_SCAN_CHARS: Final = 4000

_FAR_FUTURE: Final = datetime.max.replace(tzinfo=UTC)
_TOKEN_SPLIT: Final = re.compile(r"[\W_]+", re.UNICODE)

if not 0 < TIMELINESS_WEIGHT < min(CATEGORY_WEIGHT, EMIRATE_WEIGHT, KEYWORD_WEIGHT):
    # Guarded rather than commented: if urgency ever outweighs a real relevance signal, the
    # ranking silently becomes "soonest deadline first" wearing a relevance label.
    raise RuntimeError("The timeliness band must be the smallest, and must be positive.")


class CandidateSource(StrEnum):
    """Which rung of the fallback ladder produced the pool being ranked.

    Surfaced so the caller can log (and, if it wants, say) that the structured interpretation
    found nothing and the answer came from plain text matching instead.
    """

    #: Narrowed by the categories and emirates the query was understood to name.
    INTERPRETED = "interpreted"
    #: Substring search over the raw query, because the interpretation matched no open listing.
    TEXT = "text"
    #: Everything still open, because even the text search found nothing.
    CATALOGUE = "catalogue"


_FALLBACK_REASON: Final[dict[CandidateSource, str]] = {
    CandidateSource.INTERPRETED: "open and accepting bids",
    CandidateSource.TEXT: "matched the text of your search",
    CandidateSource.CATALOGUE: "currently open — nothing matched your search more closely",
}


@dataclass(frozen=True, slots=True)
class RankedListing:
    """One scored listing. `score` is comparable within a single response only."""

    listing: TenderListing
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchResult:
    interpretation: SearchInterpretation
    #: The model's one-sentence echo of what it understood. `SearchResponse` has no field for it
    #: yet; it is carried here rather than discarded because it is the only part of the
    #: interpretation written for a human to read.
    summary: str
    matches: tuple[RankedListing, ...]
    #: True when no language model ran. Never inferred from the results — only from the provider.
    degraded: bool
    source: CandidateSource


@dataclass(frozen=True, slots=True)
class _Keyword:
    """A search term in both the form we show and the form we match."""

    display: str
    #: Normalised and space-padded, so `in` is a whole-word phrase search rather than a
    #: substring one — "AC" must not match "accommodation".
    needle: str


@dataclass(frozen=True, slots=True)
class _Signals:
    """The interpretation, converted once into the exact types the ranker compares against."""

    categories: tuple[TenderCategory, ...]
    emirates: tuple[Emirate, ...]
    keywords: tuple[_Keyword, ...]
    budget_min: Decimal | None
    budget_max: Decimal | None

    @property
    def has_any(self) -> bool:
        return bool(
            self.categories
            or self.emirates
            or self.keywords
            or self.budget_min is not None
            or self.budget_max is not None
        )


def _normalize(text: str) -> str:
    """Fold to space-separated lowercase word tokens, padded at both ends.

    The padding is what makes a plain `in` test a word-boundary test: `" ac "` matches
    `" ... ac units "` and not `" ... accommodation "`. Accents are decomposed and their
    combining marks dropped, so "Rās al Khaimah" and "Ras Al Khaimah" reduce to the same
    tokens — decomposing without dropping them would split the word at the mark instead.

    The ASCII fast path matters: this runs over every candidate's description, and those are up
    to 20,000 characters each. `str.isascii` is a C-level check, and almost every listing takes
    the cheap branch. Splitting on `\\W` rather than `[^a-z0-9]` keeps non-Latin scripts intact
    instead of erasing an Arabic title into nothing.
    """
    clipped = text[:_MAX_SCAN_CHARS]
    if clipped.isascii():
        folded = clipped.casefold()
    else:
        decomposed = unicodedata.normalize("NFKD", clipped)
        folded = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    tokens = [token for token in _TOKEN_SPLIT.split(folded) if token]
    return f" {' '.join(tokens)} " if tokens else ""


def _to_signals(raw: RawInterpretation) -> tuple[_Signals, SearchInterpretation]:
    """Convert the provider's interpretation into ranker types and the echo the UI renders.

    Both come out of one function so the two can never disagree: whatever is dropped or clamped
    here is dropped from the ranking *and* from what the user is told we understood.
    """
    budget_min = _clamp_budget(raw.budget_min)
    budget_max = _clamp_budget(raw.budget_max)
    if budget_min is not None and budget_max is not None and budget_min > budget_max:
        # A reversed band is garbled output. Swapping would show the visitor a range they never
        # described, so the band is dropped instead and the other signals carry the query.
        logger.warning("search_budget_band_reversed")
        budget_min = budget_max = None

    keywords = tuple(
        _Keyword(display=keyword.strip(), needle=needle)
        for keyword in raw.keywords
        if (needle := _normalize(keyword))
    )
    signals = _Signals(
        categories=tuple(raw.categories),
        emirates=tuple(raw.emirates),
        keywords=keywords,
        budget_min=budget_min,
        budget_max=budget_max,
    )
    echo = SearchInterpretation(
        categories=list(raw.categories),
        emirates=list(raw.emirates),
        budget_min=budget_min,
        budget_max=budget_max,
        keywords=[keyword.display for keyword in keywords],
    )
    return signals, echo


def _text_term(query: str, signals: _Signals) -> str:
    """The single term handed to SQL for the substring rung.

    Not the raw query: `ILIKE '%we do MEP fit-out in Sharjah%'` requires that whole sentence to
    appear verbatim in a title, so it matches nothing and the fallback would fall straight
    through. The longest interpreted keyword is the most specific single term available. The raw
    query is the last resort, for input the interpreter made nothing at all of — and if that
    matches nothing either, the catalogue rung still answers with something.
    """
    if signals.keywords:
        return max((keyword.display for keyword in signals.keywords), key=len)
    return query


def _clamp_budget(value: float | None) -> Decimal | None:
    """AED floats to `Decimal` via `str`, so 1500000.0 does not become 1499999.9999999998."""
    if value is None:
        return None
    return min(Decimal(str(value)), _MAX_BUDGET)


class SearchService:
    def __init__(
        self,
        *,
        listings: TenderListingRepository,
        provider: LLMProvider,
        settings: Settings,
    ) -> None:
        self.listings = listings
        self.provider = provider
        self.settings = settings

    async def search(self, payload: SearchRequest) -> SearchResult:
        """Interpret, gather, rank. Never raises for a query it cannot make sense of."""
        # One clock for the whole request: candidates, the timeliness band, and the open/closed
        # test must all agree, and `now()` drifting between them is a real ordering bug.
        now = datetime.now(tz=UTC)
        limit = min(
            payload.limit or self.settings.search_max_results, self.settings.search_max_results
        )
        pool = min(max(limit * _POOL_MULTIPLIER, limit), _MAX_POOL)

        raw = await interpret_query(payload.query, provider=self.provider, settings=self.settings)
        signals, echo = _to_signals(raw)

        candidates, source = await self._gather(
            query=payload.query, signals=signals, pool=pool, now=now
        )
        matches = self._rank(candidates, signals=signals, source=source, now=now)[:limit]

        # The query is untrusted, unauthenticated, public text: its length is worth knowing, its
        # content is not something to write into our logs.
        logger.info(
            "search_completed",
            extra={
                "provider": getattr(self.provider, "provider_name", "unknown"),
                "query_length": len(payload.query),
                "source": source.value,
                "candidates": len(candidates),
                "matches": len(matches),
            },
        )
        return SearchResult(
            interpretation=echo,
            summary=raw.interpretation,
            matches=matches,
            degraded=self._is_degraded(),
            source=source,
        )

    def _is_degraded(self) -> bool:
        """Whether text processing, not a model, produced the interpretation."""
        return getattr(self.provider, "provider_name", "") == KeywordProvider.provider_name

    async def _gather(
        self, *, query: str, signals: _Signals, pool: int, now: datetime
    ) -> tuple[list[TenderListing], CandidateSource]:
        """Find something to rank, widening rather than returning an empty page.

        A structured interpretation that names a category nobody is tendering in is a plausible
        guess about the query, not evidence that the catalogue is empty. So it degrades to a
        substring search on the visitor's own words, and only then to the open catalogue. Every
        rung feeds the same ranker; the rung only decides which rows SQL pre-selected.
        """
        if signals.has_any:
            # Empty sequences mean "the query named none", which widens the SQL rather than
            # emptying it — the interpretation is still what ranks the result.
            rows = await self.listings.candidates_for_search(
                categories=signals.categories,
                emirates=signals.emirates,
                limit=pool,
                now=now,
            )
            if rows:
                return rows, CandidateSource.INTERPRETED

        rows, _ = await self.listings.list_public(
            ListingFilters(q=_text_term(query, signals)), limit=pool, offset=0
        )
        # `list_public` has no deadline filter, so this is the one rung that can surface a
        # tender nobody can still bid on.
        rows = [listing for listing in rows if is_open_for_applications(listing, now=now)]
        if rows:
            return rows, CandidateSource.TEXT

        return (
            await self.listings.candidates_for_search(limit=pool, now=now),
            CandidateSource.CATALOGUE,
        )

    def _rank(
        self,
        candidates: Sequence[TenderListing],
        *,
        signals: _Signals,
        source: CandidateSource,
        now: datetime,
    ) -> tuple[RankedListing, ...]:
        scored: list[tuple[Fraction, TenderListing, tuple[str, ...]]] = []
        for listing in candidates:
            # A tender nobody can still bid on is not a search result. `candidates_for_search`
            # already excludes them; the text path does not, so the test is applied uniformly.
            if not is_open_for_applications(listing, now=now):
                continue
            score, reasons = _score(listing, signals, now=now)
            if not reasons:
                reasons = (_FALLBACK_REASON[source],)
            scored.append((score, listing, reasons[:MAX_REASONS]))

        scored.sort(key=_sort_key)
        return tuple(
            RankedListing(
                listing=listing,
                # Rounded before it leaves exact arithmetic: the ordering above is already
                # decided, so this only fixes how the number renders.
                score=float(round(score, 4)),
                reasons=tuple(_trim(reason) for reason in reasons),
            )
            for score, listing, reasons in scored
        )


def _sort_key(
    entry: tuple[Fraction, TenderListing, tuple[str, ...]],
) -> tuple[Fraction, int, datetime, str]:
    """Best score first, then soonest deadline, then id — total and repeatable.

    The id is the last key on purpose: without it two listings with identical scores and
    deadlines would come back in whatever order Postgres happened to return them, and the same
    search would rank them differently on the next request.
    """
    score, listing, _ = entry
    deadline = listing.submission_deadline
    if deadline is None:
        return (-score, 1, _FAR_FUTURE, str(listing.id))
    aware = deadline if deadline.tzinfo is not None else deadline.replace(tzinfo=UTC)
    return (-score, 0, aware, str(listing.id))


def _score(
    listing: TenderListing, signals: _Signals, *, now: datetime
) -> tuple[Fraction, tuple[str, ...]]:
    """Weighted mean of the active bands, in 0..1, with the reasons that earned it."""
    bands: list[tuple[int, Fraction]] = []
    reasons: list[str] = []

    if signals.categories:
        credit = _category_credit(listing, signals.categories)
        bands.append((CATEGORY_WEIGHT, credit))
        if credit:
            reasons.append(f"category: {label_for(listing.category)}")

    if signals.emirates:
        hit = any(listing.emirate == emirate.value for emirate in signals.emirates)
        bands.append((EMIRATE_WEIGHT, Fraction(int(hit))))
        if hit:
            reasons.append(f"emirate: {label_for(listing.emirate)}")

    if signals.keywords:
        credit, matched = _keyword_credit(listing, signals.keywords)
        bands.append((KEYWORD_WEIGHT, credit))
        if matched:
            reasons.append(_mentions(matched))

    if signals.budget_min is not None or signals.budget_max is not None:
        hit = _budget_overlaps(listing, signals.budget_min, signals.budget_max)
        bands.append((BUDGET_WEIGHT, Fraction(int(hit))))
        if hit:
            reasons.append(_budget_reason(listing))

    # Always active: it needs nothing from the interpretation, and it is what keeps a listing
    # closing in six hours from outranking an equally relevant one closing in six weeks.
    bands.append((TIMELINESS_WEIGHT, _timeliness(listing, now=now)))

    total_weight = sum(weight for weight, _ in bands)
    earned = sum(weight * credit for weight, credit in bands)
    return Fraction(earned, total_weight), tuple(reasons)


def _category_credit(listing: TenderListing, categories: Sequence[TenderCategory]) -> Fraction:
    """Full credit for the strongest inferred category, tapering for the weaker ones.

    The keyword provider orders its categories strongest-signal-first and the prompt asks the
    model for the same, so a listing matching the query's primary reading should outrank one
    matching its third-best guess.
    """
    for index, category in enumerate(categories):
        if listing.category == category.value:
            return Fraction(len(categories) - index, len(categories))
    return Fraction(0)


def _keyword_credit(
    listing: TenderListing, keywords: Sequence[_Keyword]
) -> tuple[Fraction, list[str]]:
    fields = {
        "title": _normalize(listing.title),
        "summary": _normalize(listing.summary),
        "description": _normalize(listing.description),
        "tags": _normalize(" ".join(listing.tags)),
    }
    earned = 0
    matched: list[str] = []
    for keyword in keywords:
        best = max(
            (weight for name, weight in _FIELD_WEIGHTS if keyword.needle in fields[name]),
            default=0,
        )
        if best:
            earned += best
            matched.append(keyword.display)
    return Fraction(earned, len(keywords) * _MAX_FIELD_WEIGHT), matched


def _budget_overlaps(
    listing: TenderListing, wanted_min: Decimal | None, wanted_max: Decimal | None
) -> bool:
    """Range overlap, not point containment: a 1M-3M tender suits a vendor wanting "above 2M".

    A listing that disclosed no budget scores nothing here. It is not excluded from the results
    — undisclosed is not disqualifying — but claiming it matches a band nobody published would
    be an invention.
    """
    floor = listing.budget_min if listing.budget_min is not None else listing.budget_max
    ceiling = listing.budget_max if listing.budget_max is not None else listing.budget_min
    if floor is None or ceiling is None:
        return False
    if wanted_min is not None and ceiling < wanted_min:
        return False
    return not (wanted_max is not None and floor > wanted_max)


def _timeliness(listing: TenderListing, *, now: datetime) -> Fraction:
    """Half for time left to bid, half for how recently it was published.

    A listing with no deadline or no publication timestamp scores the neutral half of that
    component rather than zero: absence of a date is not evidence of urgency either way.
    """
    return (_headroom(listing, now=now) + _recency(listing, now=now)) / 2


def _headroom(listing: TenderListing, *, now: datetime) -> Fraction:
    deadline = listing.submission_deadline
    if deadline is None:
        return Fraction(1, 2)
    aware = deadline if deadline.tzinfo is not None else deadline.replace(tzinfo=UTC)
    days = (aware - now).days
    if days <= 0:
        return Fraction(0)
    return Fraction(min(days, FRESH_WINDOW_DAYS), FRESH_WINDOW_DAYS)


def _recency(listing: TenderListing, *, now: datetime) -> Fraction:
    published = listing.published_at
    if published is None:
        return Fraction(1, 2)
    aware = published if published.tzinfo is not None else published.replace(tzinfo=UTC)
    age = (now - aware).days
    if age <= 0:
        return Fraction(1)
    return Fraction(max(RECENCY_WINDOW_DAYS - age, 0), RECENCY_WINDOW_DAYS)


def _mentions(matched: Sequence[str]) -> str:
    """One reason for all keyword hits, so they cannot crowd out the other four."""
    shown = list(matched[:3])
    text = "mentions " + ", ".join(f"'{keyword}'" for keyword in shown)
    remaining = len(matched) - len(shown)
    return f"{text} and {remaining} more" if remaining else text


def _budget_reason(listing: TenderListing) -> str:
    currency = listing.currency
    if listing.budget_min is not None and listing.budget_max is not None:
        return f"budget {currency} {listing.budget_min:,.0f}-{listing.budget_max:,.0f}"
    if listing.budget_max is not None:
        return f"budget up to {currency} {listing.budget_max:,.0f}"
    # `_budget_overlaps` already established that at least one end is disclosed.
    return f"budget from {currency} {listing.budget_min:,.0f}"


def _trim(reason: str) -> str:
    """Keep a reason inside the response schema's bound without failing the whole search."""
    if len(reason) <= MAX_REASON_LENGTH:
        return reason
    return reason[: MAX_REASON_LENGTH - 1].rstrip() + "…"
