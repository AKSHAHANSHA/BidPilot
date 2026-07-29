"""The no-key provider: search interpretation derived in plain Python, with no model at all.

`docs/09` §5 requires that a deployment without an OpenAI key still answers
`POST /public/search`. Rather than a second code path through the search service, this satisfies
the same `LLMProvider` protocol and returns the same JSON the schema demands, so the service
calls one interface and validates one contract whether or not a model ran.

Two properties matter more than match quality:

* It never pretends. `provider_name` is "keyword" and `model` is not a model id, so every log
  line and any response that surfaces the provider says plainly that this was text processing.
* It refuses everything else. Requirement, risk, and metadata extraction have no honest
  keyword equivalent, so an unknown `schema_name` raises instead of returning an empty object
  that would read as "the AI found nothing".

The vocabulary below is deliberately hand-written rather than derived from the enum member
names alone: "cleaning_waste_management" is what we call it, "janitorial" is what a supplier
types.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.ai.prompts import DOCUMENT_DELIMITER, SEARCH_SCHEMA_NAME
from app.ai.providers.base import LLMProviderError, LLMResponse
from app.ai.structured_models import SearchInterpretation
from app.core.logging import get_logger
from app.domain.enums import Emirate, TenderCategory

logger = get_logger(__name__)

#: Defensive bound on the text we scan. The search service truncates the query first, but a
#: provider is handed whatever the caller renders and must limit its own work regardless.
_SCAN_LIMIT = 1000

#: Ceiling from `SearchInterpretation.categories`. Derivation must respect the schema it fills:
#: a broad query can match more than six categories, and the extras are the weakest signals.
_MAX_CATEGORIES = 6
_MAX_KEYWORDS = 10

#: How many values the echoed sentence names before it would stop being readable.
_MAX_LISTED = 4


def _normalize(query: str) -> str:
    """Lowercase, fold punctuation to spaces, collapse whitespace.

    Punctuation becomes a space rather than nothing so "fit-out", "fit out" and "oil & gas" all
    reduce to the spaced forms the term table stores. Digits and dots survive because the budget
    parser runs over the same normalized string ("1.5m", "500,000").
    """
    text = unicodedata.normalize("NFKC", query[:_SCAN_LIMIT]).lower()
    text = re.sub(r"[^a-z0-9.,$]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


#: Supplier vocabulary per category. Terms are matched whole-word against the normalized query.
_CATEGORY_TERMS: dict[TenderCategory, tuple[str, ...]] = {
    TenderCategory.CONSTRUCTION_CIVIL_WORKS: (
        "construction",
        "civil works",
        "civil engineering",
        "building works",
        "contracting",
        "concrete",
        "structural works",
        "earthworks",
        "piling",
    ),
    TenderCategory.ROADS_INFRASTRUCTURE: (
        "road",
        "roads",
        "roadworks",
        "highway",
        "highways",
        "infrastructure",
        "bridge",
        "bridges",
        "asphalt",
        "paving",
        "tunnel",
    ),
    TenderCategory.WATER_WASTEWATER: (
        "water",
        "wastewater",
        "waste water",
        "sewage",
        "sewerage",
        "desalination",
        "plumbing",
        "drainage",
        "pumping station",
    ),
    TenderCategory.ELECTRICAL_POWER: (
        "electrical",
        "electric",
        "power",
        "substation",
        "switchgear",
        "cabling",
        "hvac",
        "mep",
        "mechanical electrical",
        "generator",
        "transmission line",
    ),
    TenderCategory.OIL_GAS_PETROCHEMICAL: (
        "oil",
        "gas",
        "oil and gas",
        "petrochemical",
        "refinery",
        "pipeline",
        "upstream",
        "downstream",
        "lng",
    ),
    TenderCategory.RENEWABLE_ENERGY: (
        "renewable",
        "renewables",
        "solar",
        "photovoltaic",
        "wind farm",
        "wind energy",
        "clean energy",
        "green energy",
        "net zero",
        "ev charging",
    ),
    TenderCategory.FACILITIES_MANAGEMENT: (
        "facilities management",
        "facility management",
        "facilities",
        "fm",
        "hard services",
        "soft services",
        "building maintenance",
        "maintenance",
        "annual maintenance contract",
        "amc",
    ),
    TenderCategory.CLEANING_WASTE_MANAGEMENT: (
        "cleaning",
        "cleaner",
        "cleaners",
        "janitorial",
        "housekeeping",
        "waste",
        "waste management",
        "recycling",
        "refuse collection",
        "pest control",
    ),
    TenderCategory.LANDSCAPING_IRRIGATION: (
        "landscaping",
        "landscape",
        "irrigation",
        "gardening",
        "horticulture",
        "grounds maintenance",
        "planting",
    ),
    TenderCategory.IT_SOFTWARE: (
        "software",
        "it services",
        "it support",
        "web development",
        "website",
        "mobile app",
        "application development",
        "erp",
        "systems integration",
        "helpdesk",
        "digital transformation",
    ),
    TenderCategory.CYBERSECURITY: (
        "cybersecurity",
        "cyber security",
        "cyber",
        "information security",
        "infosec",
        "penetration testing",
        "vulnerability assessment",
        "iso 27001",
    ),
    TenderCategory.CLOUD_DATA_CENTRE: (
        "cloud",
        "data centre",
        "data center",
        "datacentre",
        "datacenter",
        "hosting",
        "aws",
        "azure",
        "server room",
        "colocation",
    ),
    TenderCategory.TELECOMMUNICATIONS: (
        "telecom",
        "telecoms",
        "telecommunications",
        "fibre",
        "fiber",
        "structured cabling",
        "network cabling",
        "5g",
        "satellite",
    ),
    TenderCategory.AI_DATA_ANALYTICS: (
        "ai",
        "artificial intelligence",
        "machine learning",
        "data analytics",
        "analytics",
        "data science",
        "business intelligence",
        "big data",
    ),
    TenderCategory.HEALTHCARE_MEDICAL: (
        "healthcare",
        "health care",
        "medical",
        "hospital",
        "clinic",
        "nursing",
        "pharmaceutical",
        "pharmacy",
        "dental",
        "ambulance",
    ),
    TenderCategory.EDUCATION_TRAINING: (
        "education",
        "training",
        "school",
        "schools",
        "university",
        "e learning",
        "elearning",
        "curriculum",
        "academy",
        "nursery",
    ),
    TenderCategory.TRANSPORT_LOGISTICS: (
        "transport",
        "transportation",
        "logistics",
        "freight",
        "shipping",
        "warehousing",
        "warehouse",
        "supply chain",
        "customs clearance",
        "courier",
    ),
    TenderCategory.FLEET_VEHICLES: (
        "fleet",
        "vehicle",
        "vehicles",
        "car rental",
        "bus",
        "buses",
        "truck",
        "trucks",
        "automotive",
        "vehicle leasing",
    ),
    TenderCategory.SECURITY_SERVICES: (
        "security",
        "security services",
        "security guard",
        "security guards",
        "guarding",
        "manned guarding",
        "cctv",
        "surveillance",
        "access control",
    ),
    TenderCategory.CATERING_HOSPITALITY: (
        "catering",
        "hospitality",
        "hotel",
        "food services",
        "canteen",
        "banquet",
        "restaurant",
    ),
    TenderCategory.PRINTING_MEDIA: (
        "printing",
        "print",
        "publishing",
        "signage",
        "photography",
        "video production",
        "media production",
        "graphic design",
        "stationery",
    ),
    TenderCategory.MARKETING_EVENTS: (
        "marketing",
        "advertising",
        "events",
        "event management",
        "exhibition",
        "exhibitions",
        "branding",
        "public relations",
        "sponsorship",
        "conference",
    ),
    TenderCategory.CONSULTING_ADVISORY: (
        "consulting",
        "consultancy",
        "advisory",
        "consultant",
        "consultants",
        "feasibility study",
        "management consulting",
    ),
    TenderCategory.LEGAL_SERVICES: (
        "legal",
        "law firm",
        "litigation",
        "legal counsel",
        "arbitration",
        "contract drafting",
        "notary",
    ),
    TenderCategory.FINANCIAL_AUDIT: (
        "audit",
        "auditing",
        "auditor",
        "accounting",
        "bookkeeping",
        "tax",
        "vat",
        "internal audit",
        "financial statements",
    ),
    TenderCategory.HR_RECRUITMENT: (
        "recruitment",
        "staffing",
        "manpower",
        "human resources",
        "hr",
        "payroll",
        "headhunting",
        "labour supply",
    ),
    TenderCategory.FURNITURE_FITOUT: (
        "furniture",
        "fit out",
        "fitout",
        "fitting out",
        "joinery",
        "interior design",
        "interiors",
        "carpentry",
        "partitions",
        "millwork",
    ),
    TenderCategory.LABORATORY_SCIENTIFIC: (
        "laboratory",
        "lab",
        "labs",
        "scientific",
        "calibration",
        "testing equipment",
        "reagents",
        "research equipment",
    ),
    TenderCategory.DEFENCE_AEROSPACE: (
        "defence",
        "defense",
        "aerospace",
        "military",
        "aviation",
        "drone",
        "drones",
        "uav",
        "radar",
    ),
    TenderCategory.ENVIRONMENTAL_SERVICES: (
        "environmental",
        "environment",
        "sustainability",
        "esg",
        "emissions",
        "pollution",
        "carbon",
        "environmental impact assessment",
    ),
}

#: Emirate names as suppliers write them: airport codes, spellings, and Al Ain, which is a city
#: in Abu Dhabi rather than an emirate of its own.
_EMIRATE_TERMS: dict[Emirate, tuple[str, ...]] = {
    Emirate.ABU_DHABI: ("abu dhabi", "abudhabi", "auh", "al ain", "alain"),
    Emirate.DUBAI: ("dubai", "dxb", "dubayy"),
    Emirate.SHARJAH: ("sharjah", "shj"),
    Emirate.AJMAN: ("ajman",),
    Emirate.UMM_AL_QUWAIN: ("umm al quwain", "umm al qaiwain", "uaq"),
    Emirate.RAS_AL_KHAIMAH: ("ras al khaimah", "ras al khaima", "rak"),
    Emirate.FUJAIRAH: ("fujairah", "fujeirah"),
}


def _compile(terms: tuple[str, ...]) -> re.Pattern[str]:
    """One whole-word alternation per vocabulary entry, longest term first.

    The lookarounds rather than `\\b` keep terms that end in a digit ("5g", "iso 27001") from
    matching inside a longer token. No capturing groups: `findall` must return whole matches.
    """
    ordered = sorted(terms, key=len, reverse=True)
    return re.compile(
        r"(?<![a-z0-9])(?:" + "|".join(re.escape(t) for t in ordered) + r")(?![a-z0-9])"
    )


_CATEGORY_PATTERNS = {category: _compile(terms) for category, terms in _CATEGORY_TERMS.items()}
_EMIRATE_PATTERNS = {emirate: _compile(terms) for emirate, terms in _EMIRATE_TERMS.items()}

#: Words that carry no search signal. "tender", "listing" and "bid" are in here because every
#: row in the catalogue is one: as a ranking keyword each matches everything, which is noise.
_STOPWORDS = frozenset(
    """
    a about above all also an and any are as at be been being bid bids but by can company contract
    contracts could do does doing done for from get give has have how if in into is it its just
    like listing listings looking looks me my need needs new not of on only opportunities
    opportunity or our out over please project projects provide provider services show showing
    some tender tenders that the their them there these they this those to under up us use want
    wants was we were what when where which who will with within work works would you your
    """.split()  # noqa: SIM905 - a hundred single-element lines would bury the list
)

_MAGNITUDES = {
    "k": 1_000.0,
    "thousand": 1_000.0,
    "m": 1_000_000.0,
    "mn": 1_000_000.0,
    "million": 1_000_000.0,
    "bn": 1_000_000_000.0,
    "billion": 1_000_000_000.0,
}

_CURRENCY = r"(?:aed|dhs|dh|dirhams|dirham|usd|\$)"

#: An amount is only an amount when it carries a currency or a magnitude. That guard is the
#: whole point: "about 30 staff" and "5 years" are numbers in a query and must not become money.
_AMOUNT_RE = re.compile(
    rf"(?:(?P<cur>{_CURRENCY})\s*)?"
    r"(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(?P<mag>million|thousand|billion|mn|bn|k|m)?(?![a-z0-9])"
    rf"(?:\s*(?P<cur2>{_CURRENCY})(?![a-z]))?"
)

_MAX_HINT = re.compile(
    r"(?:under|below|less than|up to|upto|at most|no more than|max|maximum|budget of|within)"
    r"[\sa-z]{0,12}$"
)
_MIN_HINT = re.compile(
    r"(?:over|above|more than|at least|starting|from|min|minimum|upwards of)[\sa-z]{0,12}$"
)
_RANGE_HINT = re.compile(r"between[\sa-z]{0,12}$")
_RANGE_JOIN = re.compile(r"(?:\band\b|\bto\b|-)\s*$")

#: Cap matching `SearchInterpretation.budget_*`; anything larger is a typo or an attack, and
#: silently dropping it beats failing validation on a query that was otherwise understood.
_MAX_AMOUNT = 1e12


def _amount(match: re.Match[str]) -> float | None:
    value = float(match.group("num").replace(",", ""))
    magnitude = match.group("mag")
    if magnitude:
        value *= _MAGNITUDES[magnitude]
    elif not (match.group("cur") or match.group("cur2")):
        return None  # A bare number is a count, not a budget.
    return value if 0 < value <= _MAX_AMOUNT else None


def _parse_budget(text: str) -> tuple[float | None, float | None]:
    """Read a budget band out of the query, using the words in front of each amount."""
    budget_min: float | None = None
    budget_max: float | None = None
    expecting_range_end = False

    for match in _AMOUNT_RE.finditer(text):
        value = _amount(match)
        if value is None:
            continue
        before = text[max(0, match.start() - 40) : match.start()]
        if expecting_range_end and _RANGE_JOIN.search(before):
            budget_max = value
            expecting_range_end = False
        elif _RANGE_HINT.search(before):
            budget_min = value
            expecting_range_end = True
        elif _MAX_HINT.search(before):
            budget_max = value
        elif _MIN_HINT.search(before):
            budget_min = value
        else:
            # An amount with no comparator is read as a ceiling: suppliers describe capacity as
            # "contracts of 5m", meaning that size and below, far more often than as a floor.
            budget_max = value

    if budget_min is not None and budget_max is not None and budget_min > budget_max:
        budget_min, budget_max = budget_max, budget_min
    return budget_min, budget_max


def _match_categories(text: str) -> list[TenderCategory]:
    """Categories whose vocabulary appears in the query, strongest signal first.

    Strength is the longest matched term (a two-word term is far more specific than "power")
    then the number of distinct terms matched. Enum order breaks remaining ties so the same
    query always yields the same list.
    """
    scored: list[tuple[int, int, int, TenderCategory]] = []
    for order, (category, pattern) in enumerate(_CATEGORY_PATTERNS.items()):
        hits = set(pattern.findall(text))
        if not hits:
            continue
        scored.append((max(len(hit.split()) for hit in hits), len(hits), -order, category))
    scored.sort(reverse=True)
    return [category for *_, category in scored[:_MAX_CATEGORIES]]


def _match_emirates(text: str) -> list[Emirate]:
    return [emirate for emirate, pattern in _EMIRATE_PATTERNS.items() if pattern.search(text)]


def _match_keywords(text: str) -> list[str]:
    """The query's own content words, deduplicated, in the order the supplier wrote them."""
    keywords: list[str] = []
    for token in text.split():
        word = token.strip(".,")
        if len(word) < 2 or not word[0].isalpha() or word in _STOPWORDS or word in keywords:
            continue
        keywords.append(word[:40])
        if len(keywords) == _MAX_KEYWORDS:
            break
    return keywords


def _label(value: str) -> str:
    return value.replace("_", " ")


def _summarise(
    categories: list[TenderCategory],
    emirates: list[Emirate],
    keywords: list[str],
    budget_min: float | None,
    budget_max: float | None,
) -> str:
    """One sentence for the UI. It says "keyword match" because that is what happened."""
    parts: list[str] = []
    if categories:
        parts.append(", ".join(_label(c.value) for c in categories[:_MAX_LISTED]))
    elif keywords:
        parts.append("listings mentioning " + ", ".join(keywords[:_MAX_LISTED]))
    else:
        parts.append("all published listings")

    if emirates:
        parts.append("in " + " or ".join(_label(e.value).title() for e in emirates[:_MAX_LISTED]))

    if budget_min is not None and budget_max is not None:
        parts.append(f"with a budget between AED {budget_min:,.0f} and AED {budget_max:,.0f}")
    elif budget_max is not None:
        parts.append(f"with a budget up to AED {budget_max:,.0f}")
    elif budget_min is not None:
        parts.append(f"with a budget from AED {budget_min:,.0f}")

    return f"Keyword match: {' '.join(parts)}."[:280]


def derive_interpretation(query: str) -> SearchInterpretation:
    """Map a free-text query onto the controlled vocabularies with no model involved.

    Also the search service's fallback when a provider fails or answers unusably, so it must
    never raise on any input: an unrecognisable query yields an empty interpretation, which the
    ranker reads as "no constraints".
    """
    text = _normalize(query)
    if not text:
        return SearchInterpretation(interpretation="Keyword match: all published listings.")

    categories = _match_categories(text)
    emirates = _match_emirates(text)
    keywords = _match_keywords(text)
    budget_min, budget_max = _parse_budget(text)
    return SearchInterpretation(
        categories=categories,
        emirates=emirates,
        keywords=keywords,
        budget_min=budget_min,
        budget_max=budget_max,
        interpretation=_summarise(categories, emirates, keywords, budget_min, budget_max),
    )


def _unwrap_query(user: str) -> str:
    """Recover the query from the rendered user message.

    The provider is handed the delimited message every other provider receives, so it has to
    undo `Prompt.render_user`. If the delimiters are missing the whole message is the query;
    the text is inert data here either way, since nothing in it is ever executed.
    """
    parts = user.split(DOCUMENT_DELIMITER)
    return parts[1].strip() if len(parts) >= 3 else user.strip()


class KeywordProvider:
    """Answers the search schema from text alone. No network, no key, no model."""

    #: Not a model id, on purpose: it appears in logs and must never read as one.
    model = "keyword-rules"
    provider_name = "keyword"

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str,
        temperature: float | None = None,
    ) -> LLMResponse:
        if schema_name != SEARCH_SCHEMA_NAME:
            raise LLMProviderError(
                f"No AI provider is configured, so {schema_name!r} cannot be produced. "
                "Set OPENAI_API_KEY and OPENAI_MODEL to enable document analysis; only "
                f"{SEARCH_SCHEMA_NAME!r} has a keyword equivalent."
            )
        interpretation = derive_interpretation(_unwrap_query(user))
        logger.info(
            "keyword_interpretation_derived",
            extra={
                "categories": len(interpretation.categories),
                "emirates": len(interpretation.emirates),
                "keywords": len(interpretation.keywords),
            },
        )
        # Zero tokens is the literal truth and keeps cost estimation honest for this path.
        return LLMResponse(
            content=interpretation.model_dump_json(),
            input_tokens=0,
            output_tokens=0,
            provider=self.provider_name,
            model=self.model,
        )
