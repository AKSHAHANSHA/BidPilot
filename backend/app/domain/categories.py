"""Marketplace project categories.

Kept as a Python constant, not a database check constraint, because this list is a
display/filter taxonomy that can grow with a code change alone — it does not have the same
"typo silently hides a record" risk as the evidence vocabulary (which every requirement
is matched against). Sourced from common UAE public-sector procurement categories.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProjectCategory:
    slug: str
    label: str
    icon: str  # emoji hint the frontend can use as a lightweight visual


PROJECT_CATEGORIES: tuple[ProjectCategory, ...] = (
    ProjectCategory("construction", "Construction & Civil Works", "\U0001f3d7️"),
    ProjectCategory("facilities_management", "Facilities Management", "\U0001f3e2"),
    ProjectCategory("it_services", "IT Services & Software", "\U0001f4bb"),
    ProjectCategory("healthcare", "Healthcare & Medical", "\U0001fa7a"),
    ProjectCategory("engineering", "Engineering Consultancy", "\U0001f4d0"),
    ProjectCategory("catering", "Catering & Food Services", "\U0001f37d️"),
    ProjectCategory("cleaning", "Cleaning Services", "\U0001f9f9"),
    ProjectCategory("security", "Security Services", "\U0001f6e1️"),
    ProjectCategory("transport", "Transport & Logistics", "\U0001f69a"),
    ProjectCategory("education", "Education & Training", "\U0001f393"),
    ProjectCategory("environmental", "Environmental Services", "\U0001f33f"),
    ProjectCategory("energy_utilities", "Energy & Utilities", "⚡"),
    ProjectCategory("telecom", "Telecommunications", "\U0001f4e1"),
    ProjectCategory("media", "Printing, Media & Design", "\U0001f5a8️"),
    ProjectCategory("real_estate", "Real Estate Services", "\U0001f3e0"),
    ProjectCategory("events", "Event Management", "\U0001f389"),
    ProjectCategory("translation", "Translation & Interpretation", "\U0001f4ac"),
    ProjectCategory("waste_management", "Waste Management", "\U0001f5d1️"),
    ProjectCategory("medical_equipment", "Medical Equipment Supply", "\U0001fa7a"),
    ProjectCategory("office_supplies", "Office Supplies", "\U0001f4ce"),
    ProjectCategory("uniforms_ppe", "Uniforms & PPE", "\U0001f9ba"),
    ProjectCategory("marketing", "Marketing & Advertising", "\U0001f4e3"),
    ProjectCategory("legal_advisory", "Legal & Advisory", "⚖️"),
    ProjectCategory("financial_audit", "Financial Audit & Accounting", "\U0001f4ca"),
)

CATEGORY_SLUGS: frozenset[str] = frozenset(c.slug for c in PROJECT_CATEGORIES)


def is_valid_category(slug: str) -> bool:
    return slug in CATEGORY_SLUGS


def category_label(slug: str) -> str:
    for category in PROJECT_CATEGORIES:
        if category.slug == slug:
            return category.label
    return slug.replace("_", " ").title()
