"""Fictional but plausible content for the portal demo.

Templates rather than a frozen JSON blob: a static fixture of fifty tenders would be fifty
copies of the same six fields to maintain, and every deadline in it would be in the past a
month after it was written. Here the shape is declared once per category and the seeder
renders it against today's date.

Nothing in this file is real. Buyer names are invented; any resemblance to an actual UAE
authority or supplier is coincidental. Contract values are illustrative.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import Emirate, RequiredDocumentType, TenderCategory

# --- Buyers ---------------------------------------------------------------------------------

#: Invented buying organisations. Each publishes in a handful of categories, so the demo feed
#: looks like a marketplace rather than one authority talking to itself.
BUYERS: tuple[dict[str, object], ...] = (
    {
        "name": "Emirates Urban Development Authority",
        "description": (
            "Fictional civic developer responsible for master-planned districts, roads and "
            "public realm across the northern emirates."
        ),
        "emirate": Emirate.SHARJAH.value,
        "city": "Sharjah",
        "industry": "Urban development",
        "categories": (
            TenderCategory.CONSTRUCTION_CIVIL_WORKS,
            TenderCategory.ROADS_INFRASTRUCTURE,
            TenderCategory.LANDSCAPING_IRRIGATION,
            TenderCategory.FURNITURE_FITOUT,
            TenderCategory.ENVIRONMENTAL_SERVICES,
        ),
    },
    {
        "name": "Gulf Water & Power Company",
        "description": (
            "Fictional utility operating desalination, distribution and grid assets, "
            "procuring plant, maintenance and engineering services."
        ),
        "emirate": Emirate.ABU_DHABI.value,
        "city": "Abu Dhabi",
        "industry": "Utilities",
        "categories": (
            TenderCategory.WATER_WASTEWATER,
            TenderCategory.ELECTRICAL_POWER,
            TenderCategory.RENEWABLE_ENERGY,
            TenderCategory.OIL_GAS_PETROCHEMICAL,
            TenderCategory.LABORATORY_SCIENTIFIC,
        ),
    },
    {
        "name": "Dubai Digital Government Office",
        "description": (
            "Fictional central technology office procuring platforms, security services and "
            "data capability for public bodies."
        ),
        "emirate": Emirate.DUBAI.value,
        "city": "Dubai",
        "industry": "Government technology",
        "categories": (
            TenderCategory.IT_SOFTWARE,
            TenderCategory.CYBERSECURITY,
            TenderCategory.CLOUD_DATA_CENTRE,
            TenderCategory.AI_DATA_ANALYTICS,
            TenderCategory.TELECOMMUNICATIONS,
        ),
    },
    {
        "name": "Northern Emirates Health Trust",
        "description": (
            "Fictional healthcare group running hospitals and clinics, procuring clinical "
            "supplies, facilities and training."
        ),
        "emirate": Emirate.RAS_AL_KHAIMAH.value,
        "city": "Ras Al Khaimah",
        "industry": "Healthcare",
        "categories": (
            TenderCategory.HEALTHCARE_MEDICAL,
            TenderCategory.CLEANING_WASTE_MANAGEMENT,
            TenderCategory.CATERING_HOSPITALITY,
            TenderCategory.FACILITIES_MANAGEMENT,
            TenderCategory.EDUCATION_TRAINING,
        ),
    },
    {
        "name": "Al Manara Transport Corporation",
        "description": (
            "Fictional public transport operator procuring fleet, depots, logistics and "
            "passenger services."
        ),
        "emirate": Emirate.AJMAN.value,
        "city": "Ajman",
        "industry": "Transport",
        "categories": (
            TenderCategory.TRANSPORT_LOGISTICS,
            TenderCategory.FLEET_VEHICLES,
            TenderCategory.SECURITY_SERVICES,
            TenderCategory.PRINTING_MEDIA,
            TenderCategory.MARKETING_EVENTS,
        ),
    },
    {
        "name": "Federal Procurement Shared Services",
        "description": (
            "Fictional shared-service body running framework competitions for professional "
            "and corporate services on behalf of smaller entities."
        ),
        "emirate": Emirate.FUJAIRAH.value,
        "city": "Fujairah",
        "industry": "Shared services",
        "categories": (
            TenderCategory.CONSULTING_ADVISORY,
            TenderCategory.LEGAL_SERVICES,
            TenderCategory.FINANCIAL_AUDIT,
            TenderCategory.HR_RECRUITMENT,
            TenderCategory.DEFENCE_AEROSPACE,
        ),
    },
)

# --- Document checklists --------------------------------------------------------------------

D = RequiredDocumentType

#: Every tender asks for these. Kept small: a checklist nobody can satisfy is not a demo of
#: screening, it is a demo of failure.
BASE_MANDATORY: tuple[RequiredDocumentType, ...] = (
    D.TRADE_LICENCE,
    D.COMMERCIAL_REGISTRATION,
    D.VAT_TAX_CERTIFICATE,
    D.COMPANY_PROFILE,
)

BASE_OPTIONAL: tuple[RequiredDocumentType, ...] = (
    D.CLIENT_TESTIMONIAL,
    D.ORGANISATION_CHART,
)

#: Extra requirements that fit the work. A construction tender asking for a method statement
#: and an HSE plan is the kind of detail that makes the demo read as real procurement.
CATEGORY_REQUIREMENTS: dict[TenderCategory, tuple[tuple[RequiredDocumentType, bool], ...]] = {
    TenderCategory.CONSTRUCTION_CIVIL_WORKS: (
        (D.BID_BOND, True),
        (D.HSE_PLAN, True),
        (D.METHOD_STATEMENT, True),
        (D.AUDITED_FINANCIALS, True),
        (D.EQUIPMENT_LIST, False),
        (D.PROJECT_SCHEDULE, False),
        (D.PAST_PROJECT_REFERENCES, True),
    ),
    TenderCategory.ROADS_INFRASTRUCTURE: (
        (D.BID_BOND, True),
        (D.HSE_PLAN, True),
        (D.METHOD_STATEMENT, True),
        (D.EQUIPMENT_LIST, True),
        (D.PAST_PROJECT_REFERENCES, True),
        (D.PROJECT_SCHEDULE, False),
    ),
    TenderCategory.WATER_WASTEWATER: (
        (D.ISO_CERTIFICATION, True),
        (D.HSE_PLAN, True),
        (D.TECHNICAL_PROPOSAL, True),
        (D.AUDITED_FINANCIALS, True),
        (D.STAFF_CVS, False),
    ),
    TenderCategory.ELECTRICAL_POWER: (
        (D.ISO_CERTIFICATION, True),
        (D.TECHNICAL_PROPOSAL, True),
        (D.INSURANCE_CERTIFICATE, True),
        (D.STAFF_CVS, False),
        (D.EQUIPMENT_LIST, False),
    ),
    TenderCategory.OIL_GAS_PETROCHEMICAL: (
        (D.HSE_PLAN, True),
        (D.ISO_CERTIFICATION, True),
        (D.INSURANCE_CERTIFICATE, True),
        (D.PERFORMANCE_GUARANTEE, True),
        (D.AUDITED_FINANCIALS, True),
    ),
    TenderCategory.RENEWABLE_ENERGY: (
        (D.TECHNICAL_PROPOSAL, True),
        (D.AUDITED_FINANCIALS, True),
        (D.PAST_PROJECT_REFERENCES, True),
        (D.PROJECT_SCHEDULE, False),
    ),
    TenderCategory.FACILITIES_MANAGEMENT: (
        (D.INSURANCE_CERTIFICATE, True),
        (D.HSE_PLAN, True),
        (D.STAFF_CVS, False),
        (D.QUALITY_PLAN, False),
        (D.PAST_PROJECT_REFERENCES, True),
    ),
    TenderCategory.CLEANING_WASTE_MANAGEMENT: (
        (D.HSE_PLAN, True),
        (D.INSURANCE_CERTIFICATE, True),
        (D.EQUIPMENT_LIST, False),
        (D.METHOD_STATEMENT, False),
    ),
    TenderCategory.LANDSCAPING_IRRIGATION: (
        (D.METHOD_STATEMENT, True),
        (D.EQUIPMENT_LIST, False),
        (D.PAST_PROJECT_REFERENCES, False),
    ),
    TenderCategory.IT_SOFTWARE: (
        (D.TECHNICAL_PROPOSAL, True),
        (D.COMMERCIAL_PROPOSAL, True),
        (D.STAFF_CVS, True),
        (D.PAST_PROJECT_REFERENCES, True),
        (D.PROJECT_SCHEDULE, False),
    ),
    TenderCategory.CYBERSECURITY: (
        (D.ISO_CERTIFICATION, True),
        (D.TECHNICAL_PROPOSAL, True),
        (D.STAFF_CVS, True),
        (D.INSURANCE_CERTIFICATE, False),
    ),
    TenderCategory.CLOUD_DATA_CENTRE: (
        (D.ISO_CERTIFICATION, True),
        (D.TECHNICAL_PROPOSAL, True),
        (D.AUDITED_FINANCIALS, True),
        (D.QUALITY_PLAN, False),
    ),
    TenderCategory.TELECOMMUNICATIONS: (
        (D.TECHNICAL_PROPOSAL, True),
        (D.EQUIPMENT_LIST, True),
        (D.PROJECT_SCHEDULE, False),
    ),
    TenderCategory.AI_DATA_ANALYTICS: (
        (D.TECHNICAL_PROPOSAL, True),
        (D.STAFF_CVS, True),
        (D.PAST_PROJECT_REFERENCES, False),
    ),
    TenderCategory.HEALTHCARE_MEDICAL: (
        (D.ISO_CERTIFICATION, True),
        (D.INSURANCE_CERTIFICATE, True),
        (D.TECHNICAL_PROPOSAL, True),
        (D.QUALITY_PLAN, True),
    ),
    TenderCategory.EDUCATION_TRAINING: (
        (D.STAFF_CVS, True),
        (D.TECHNICAL_PROPOSAL, True),
        (D.PAST_PROJECT_REFERENCES, False),
    ),
    TenderCategory.TRANSPORT_LOGISTICS: (
        (D.INSURANCE_CERTIFICATE, True),
        (D.EQUIPMENT_LIST, True),
        (D.HSE_PLAN, False),
    ),
    TenderCategory.FLEET_VEHICLES: (
        (D.COMMERCIAL_PROPOSAL, True),
        (D.EQUIPMENT_LIST, True),
        (D.PERFORMANCE_GUARANTEE, False),
    ),
    TenderCategory.SECURITY_SERVICES: (
        (D.STAFF_CVS, True),
        (D.INSURANCE_CERTIFICATE, True),
        (D.HSE_PLAN, False),
    ),
    TenderCategory.CATERING_HOSPITALITY: (
        (D.ISO_CERTIFICATION, True),
        (D.INSURANCE_CERTIFICATE, True),
        (D.METHOD_STATEMENT, False),
    ),
    TenderCategory.PRINTING_MEDIA: ((D.COMMERCIAL_PROPOSAL, True), (D.EQUIPMENT_LIST, False)),
    TenderCategory.MARKETING_EVENTS: (
        (D.TECHNICAL_PROPOSAL, True),
        (D.PAST_PROJECT_REFERENCES, True),
        (D.STAFF_CVS, False),
    ),
    TenderCategory.CONSULTING_ADVISORY: (
        (D.STAFF_CVS, True),
        (D.TECHNICAL_PROPOSAL, True),
        (D.PAST_PROJECT_REFERENCES, True),
    ),
    TenderCategory.LEGAL_SERVICES: ((D.STAFF_CVS, True), (D.AUTHORISED_SIGNATORY, True)),
    TenderCategory.FINANCIAL_AUDIT: (
        (D.AUDITED_FINANCIALS, True),
        (D.STAFF_CVS, True),
        (D.BANK_REFERENCE_LETTER, False),
    ),
    TenderCategory.HR_RECRUITMENT: ((D.STAFF_CVS, True), (D.COMMERCIAL_PROPOSAL, True)),
    TenderCategory.FURNITURE_FITOUT: (
        (D.METHOD_STATEMENT, True),
        (D.PROJECT_SCHEDULE, True),
        (D.PAST_PROJECT_REFERENCES, False),
    ),
    TenderCategory.LABORATORY_SCIENTIFIC: (
        (D.ISO_CERTIFICATION, True),
        (D.EQUIPMENT_LIST, True),
        (D.TECHNICAL_PROPOSAL, True),
    ),
    TenderCategory.DEFENCE_AEROSPACE: (
        (D.ISO_CERTIFICATION, True),
        (D.PERFORMANCE_GUARANTEE, True),
        (D.AUDITED_FINANCIALS, True),
        (D.AUTHORISED_SIGNATORY, True),
    ),
    TenderCategory.ENVIRONMENTAL_SERVICES: (
        (D.HSE_PLAN, True),
        (D.METHOD_STATEMENT, True),
        (D.ISO_CERTIFICATION, False),
    ),
}


@dataclass(frozen=True, slots=True)
class ListingTemplate:
    """One renderable tender for a category."""

    title: str
    summary: str
    description: str
    #: Inclusive AED range the seeder picks a budget band from.
    budget: tuple[int, int]
    duration_months: int
    tags: tuple[str, ...] = field(default_factory=tuple)
    min_years_experience: int | None = None
    requires_bid_bond: bool = False


def _body(scope: str, obligations: str) -> str:
    """Assemble a description in the register a real tender notice uses."""
    return (
        f"{scope}\n\n"
        "Scope of works\n"
        f"{obligations}\n\n"
        "Submission\n"
        "Bidders must submit a technical and commercial proposal, together with every document "
        "listed in the requirement checklist. Submissions that omit a mandatory document will "
        "not be evaluated. Clarification questions must be raised before the questions deadline; "
        "responses will be issued to all registered bidders.\n\n"
        "Evaluation\n"
        "Proposals are assessed on technical capability, relevant experience, delivery "
        "programme and price. The buying body is not bound to accept the lowest or any bid."
    )


#: Two to three templates per category so the feed does not repeat a title.
TEMPLATES: dict[TenderCategory, tuple[ListingTemplate, ...]] = {
    TenderCategory.CONSTRUCTION_CIVIL_WORKS: (
        ListingTemplate(
            title="Construction of a four-storey community centre, Al Nahda",
            summary=(
                "Design-and-build of a 6,200 m² community centre including hall, library and "
                "parking podium, delivered over 20 months."
            ),
            description=_body(
                "The Authority intends to appoint a main contractor for the construction of a "
                "four-storey community centre on a cleared plot in Al Nahda.",
                "Substructure and superstructure, envelope, MEP first and second fix, internal "
                "fit-out, external works and landscaping, and a 12-month defects liability "
                "period.",
            ),
            budget=(18_000_000, 24_000_000),
            duration_months=20,
            tags=("design and build", "civil works", "community"),
            min_years_experience=8,
            requires_bid_bond=True,
        ),
        ListingTemplate(
            title="Structural strengthening of two municipal car parks",
            summary=(
                "Concrete repair, post-tension remediation and waterproofing across two "
                "multi-storey car parks, phased to keep half of each open."
            ),
            description=_body(
                "Remedial structural works to two municipal multi-storey car parks identified "
                "in the Authority's condition survey.",
                "Concrete repair, cathodic protection, replacement of movement joints, deck "
                "waterproofing, line marking, and phased traffic management.",
            ),
            budget=(4_500_000, 6_200_000),
            duration_months=11,
            tags=("remedial", "structures"),
            min_years_experience=5,
            requires_bid_bond=True,
        ),
    ),
    TenderCategory.ROADS_INFRASTRUCTURE: (
        ListingTemplate(
            title="Dualling of 7.4 km arterial road with three signalised junctions",
            summary=(
                "Widening an existing single carriageway to dual two-lane, including drainage, "
                "lighting, and three upgraded signalised junctions."
            ),
            description=_body(
                "The Authority seeks a contractor to dual a 7.4 km arterial route serving new "
                "residential districts.",
                "Earthworks, pavement construction, stormwater drainage, street lighting, "
                "signalised junction upgrades, signage and road marking, and diversion works "
                "for existing utilities.",
            ),
            budget=(52_000_000, 68_000_000),
            duration_months=26,
            tags=("highways", "junction upgrade"),
            min_years_experience=10,
            requires_bid_bond=True,
        ),
        ListingTemplate(
            title="Three-year road maintenance and resurfacing framework",
            summary=(
                "Call-off framework for reactive and planned carriageway repair across the "
                "northern district road network."
            ),
            description=_body(
                "A three-year framework for planned and reactive maintenance of the district "
                "road network.",
                "Pothole repair, patching, surface dressing, resurfacing, gully cleansing and "
                "emergency callout within agreed response times.",
            ),
            budget=(12_000_000, 20_000_000),
            duration_months=36,
            tags=("framework", "maintenance"),
            min_years_experience=6,
        ),
    ),
    TenderCategory.WATER_WASTEWATER: (
        ListingTemplate(
            title="Upgrade of a 40,000 m³/day wastewater treatment plant",
            summary=(
                "Process upgrade to meet revised discharge standards, including new aeration, "
                "sludge handling and SCADA integration."
            ),
            description=_body(
                "The Company requires a contractor to upgrade an operational wastewater "
                "treatment plant while maintaining continuous treatment.",
                "Replacement of aeration equipment, new sludge dewatering, tertiary filtration, "
                "instrumentation, SCADA integration, commissioning and operator training.",
            ),
            budget=(75_000_000, 96_000_000),
            duration_months=30,
            tags=("process", "SCADA", "commissioning"),
            min_years_experience=10,
            requires_bid_bond=True,
        ),
        ListingTemplate(
            title="Supply and installation of district water network leak detection",
            summary=(
                "Acoustic and pressure-based leak detection across 320 km of distribution main, "
                "with a two-year monitoring service."
            ),
            description=_body(
                "Deployment of a permanent leak-detection capability across the distribution "
                "network.",
                "Supply, install and commission acoustic loggers and pressure sensors, "
                "integrate telemetry, and provide a two-year monitoring and reporting service.",
            ),
            budget=(9_000_000, 13_500_000),
            duration_months=28,
            tags=("non-revenue water", "telemetry"),
            min_years_experience=5,
        ),
    ),
    TenderCategory.ELECTRICAL_POWER: (
        ListingTemplate(
            title="Construction of a 132/11 kV primary substation",
            summary=(
                "Turnkey substation including GIS switchgear, transformers, protection and "
                "grid connection."
            ),
            description=_body(
                "Turnkey delivery of a new 132/11 kV primary substation to serve a growing "
                "industrial area.",
                "Civil works, GIS switchgear, power transformers, protection and control, "
                "auxiliary systems, cable terminations, testing and energisation.",
            ),
            budget=(44_000_000, 58_000_000),
            duration_months=24,
            tags=("substation", "GIS", "turnkey"),
            min_years_experience=10,
            requires_bid_bond=True,
        ),
        ListingTemplate(
            title="Replacement of street lighting with centrally managed LED",
            summary=(
                "Retrofit of 14,000 luminaires to LED with a central management system and "
                "five-year warranty."
            ),
            description=_body(
                "Retrofit of the district's street lighting stock to LED with remote management.",
                "Survey, supply and install luminaires, install nodes and gateways, configure "
                "the central management system, and dispose of removed fittings responsibly.",
            ),
            budget=(21_000_000, 27_000_000),
            duration_months=18,
            tags=("LED", "energy efficiency", "CMS"),
            min_years_experience=6,
        ),
    ),
    TenderCategory.OIL_GAS_PETROCHEMICAL: (
        ListingTemplate(
            title="Shutdown maintenance services for a gas processing train",
            summary=(
                "Planned turnaround covering mechanical, static equipment and instrumentation "
                "works within a fixed 21-day window."
            ),
            description=_body(
                "Provision of turnaround maintenance for one gas processing train during a "
                "fixed shutdown window.",
                "Vessel entry and inspection, heat exchanger cleaning, valve overhaul, "
                "instrument loop checks, and reinstatement to operating condition.",
            ),
            budget=(31_000_000, 42_000_000),
            duration_months=6,
            tags=("turnaround", "shutdown", "static equipment"),
            min_years_experience=10,
            requires_bid_bond=True,
        ),
    ),
    TenderCategory.RENEWABLE_ENERGY: (
        ListingTemplate(
            title="Rooftop solar PV across eleven public buildings",
            summary=(
                "Design, supply and install 6.8 MWp of rooftop PV with monitoring and a "
                "ten-year performance guarantee."
            ),
            description=_body(
                "Delivery of rooftop photovoltaic generation across a portfolio of public "
                "buildings.",
                "Structural assessment, design, supply and installation of modules, inverters "
                "and monitoring, grid connection approvals, and ten years of performance "
                "reporting.",
            ),
            budget=(28_000_000, 36_000_000),
            duration_months=16,
            tags=("solar PV", "net metering"),
            min_years_experience=5,
        ),
        ListingTemplate(
            title="Feasibility study for a 60 MW battery storage facility",
            summary=(
                "Technical and commercial feasibility for grid-scale storage, including siting, "
                "grid impact and financial modelling."
            ),
            description=_body(
                "A feasibility study to establish whether a grid-scale battery facility is "
                "viable at three candidate sites.",
                "Site assessment, technology comparison, grid impact study, permitting review, "
                "capital and operating cost modelling, and a recommended option with a "
                "delivery roadmap.",
            ),
            budget=(1_800_000, 2_600_000),
            duration_months=8,
            tags=("BESS", "feasibility", "grid"),
            min_years_experience=5,
        ),
    ),
    TenderCategory.FACILITIES_MANAGEMENT: (
        ListingTemplate(
            title="Integrated facilities management for a hospital campus",
            summary=(
                "Five-year integrated hard and soft FM across a 480-bed hospital campus, with "
                "24/7 helpdesk cover."
            ),
            description=_body(
                "Integrated facilities management for an operational hospital campus, where "
                "clinical continuity is the overriding constraint.",
                "Planned and reactive maintenance of building services, medical gas systems, "
                "cleaning to clinical standards, waste segregation, portering, grounds "
                "maintenance and a 24/7 helpdesk.",
            ),
            budget=(64_000_000, 82_000_000),
            duration_months=60,
            tags=("IFM", "healthcare", "24/7"),
            min_years_experience=8,
            requires_bid_bond=True,
        ),
        ListingTemplate(
            title="Hard FM services for eleven civic buildings",
            summary=(
                "Three-year planned and reactive maintenance of HVAC, electrical, plumbing and "
                "fire systems across a civic portfolio."
            ),
            description=_body(
                "Hard facilities management across a portfolio of civic buildings.",
                "Planned preventative maintenance, reactive callouts within agreed response "
                "times, statutory inspections, and asset condition reporting.",
            ),
            budget=(15_000_000, 21_000_000),
            duration_months=36,
            tags=("hard FM", "PPM"),
            min_years_experience=5,
        ),
    ),
    TenderCategory.CLEANING_WASTE_MANAGEMENT: (
        ListingTemplate(
            title="Clinical and general waste collection for health facilities",
            summary=(
                "Segregated collection, transport and treatment of clinical, pharmaceutical and "
                "general waste across nineteen sites."
            ),
            description=_body(
                "Collection and compliant disposal of waste streams generated across the "
                "Trust's facilities.",
                "Supply of containers, scheduled and on-call collection, licensed transport, "
                "treatment and disposal, and monthly duty-of-care reporting.",
            ),
            budget=(11_000_000, 16_000_000),
            duration_months=36,
            tags=("clinical waste", "duty of care"),
            min_years_experience=5,
        ),
    ),
    TenderCategory.LANDSCAPING_IRRIGATION: (
        ListingTemplate(
            title="Softscape and smart irrigation for a 42-hectare district park",
            summary=(
                "Planting, turfing and a moisture-sensing irrigation system designed to cut "
                "consumption by a third."
            ),
            description=_body(
                "Landscape delivery for a new district park, with water efficiency as a stated "
                "objective.",
                "Soil preparation, tree and shrub planting, turfing, drip and subsurface "
                "irrigation, moisture sensing and central control, and 24 months of "
                "establishment maintenance.",
            ),
            budget=(7_500_000, 10_500_000),
            duration_months=22,
            tags=("softscape", "smart irrigation", "water saving"),
            min_years_experience=4,
        ),
    ),
    TenderCategory.IT_SOFTWARE: (
        ListingTemplate(
            title="Build of a unified citizen services portal",
            summary=(
                "Design and build of a single portal consolidating 40+ services, with identity "
                "integration and Arabic/English parity."
            ),
            description=_body(
                "Delivery of a unified citizen services portal replacing a fragmented estate of "
                "departmental websites.",
                "Discovery, service design, accessible front-end, integration with the national "
                "identity provider and existing back-office systems, full Arabic and English "
                "parity, load testing, and a 12-month hypercare period.",
            ),
            budget=(14_000_000, 19_500_000),
            duration_months=22,
            tags=("digital services", "accessibility", "bilingual"),
            min_years_experience=6,
            requires_bid_bond=True,
        ),
        ListingTemplate(
            title="Replacement of the corporate ERP finance module",
            summary=(
                "Implementation and data migration for a replacement finance module across six "
                "entities."
            ),
            description=_body(
                "Replacement of an end-of-life finance module within the corporate ERP estate.",
                "Requirements confirmation, configuration, data migration and reconciliation, "
                "integration with procurement and payroll, training, and parallel-run support.",
            ),
            budget=(8_500_000, 12_000_000),
            duration_months=18,
            tags=("ERP", "migration", "finance"),
            min_years_experience=6,
        ),
    ),
    TenderCategory.CYBERSECURITY: (
        ListingTemplate(
            title="Managed detection and response for government workloads",
            summary=(
                "24/7 monitoring, threat hunting and incident response across cloud and "
                "on-premise estates."
            ),
            description=_body(
                "Provision of a managed detection and response capability covering the Office's "
                "hosted and on-premise workloads.",
                "Log ingestion and tuning, 24/7 monitoring, threat hunting, incident triage and "
                "response, quarterly purple-team exercises, and monthly reporting to the "
                "security committee.",
            ),
            budget=(9_000_000, 13_000_000),
            duration_months=36,
            tags=("MDR", "SOC", "incident response"),
            min_years_experience=6,
        ),
        ListingTemplate(
            title="Penetration testing and secure code review panel",
            summary=(
                "Call-off panel for application, infrastructure and cloud testing with agreed "
                "turnaround times."
            ),
            description=_body(
                "Establishment of a panel of suppliers to deliver security testing on demand.",
                "Web and mobile application testing, infrastructure and cloud configuration "
                "review, secure code review, retesting of remediated findings, and executive "
                "reporting.",
            ),
            budget=(2_400_000, 4_000_000),
            duration_months=24,
            tags=("pentest", "code review", "panel"),
            min_years_experience=4,
        ),
    ),
    TenderCategory.CLOUD_DATA_CENTRE: (
        ListingTemplate(
            title="Migration of 220 workloads to a sovereign cloud platform",
            summary=(
                "Assessment, migration and optimisation of legacy workloads with a data "
                "residency constraint."
            ),
            description=_body(
                "Migration of the legacy application estate onto a sovereign cloud platform.",
                "Discovery and dependency mapping, migration wave planning, execution, "
                "application remediation, cost optimisation, and knowledge transfer.",
            ),
            budget=(17_000_000, 24_000_000),
            duration_months=24,
            tags=("cloud migration", "data residency"),
            min_years_experience=7,
            requires_bid_bond=True,
        ),
    ),
    TenderCategory.TELECOMMUNICATIONS: (
        ListingTemplate(
            title="Campus-wide private 5G network for a logistics hub",
            summary=(
                "Design, supply and operate a private 5G network covering 180 hectares of yard "
                "and warehousing."
            ),
            description=_body(
                "Deployment of a private cellular network to support automated handling "
                "equipment across a logistics campus.",
                "Radio planning, core and RAN supply, installation, spectrum coordination, "
                "device onboarding, and three years of managed operation.",
            ),
            budget=(23_000_000, 31_000_000),
            duration_months=20,
            tags=("private 5G", "industrial"),
            min_years_experience=6,
        ),
    ),
    TenderCategory.AI_DATA_ANALYTICS: (
        ListingTemplate(
            title="Demand forecasting platform for utility load planning",
            summary=(
                "Build a forecasting capability over historical load, weather and development "
                "data, with explainable outputs."
            ),
            description=_body(
                "Delivery of a demand forecasting platform to support network planning decisions.",
                "Data engineering, model development and validation, an explainability layer "
                "that planners can interrogate, integration with planning tooling, and handover "
                "with documented retraining procedures.",
            ),
            budget=(6_500_000, 9_000_000),
            duration_months=16,
            tags=("forecasting", "explainability", "MLOps"),
            min_years_experience=5,
        ),
    ),
    TenderCategory.HEALTHCARE_MEDICAL: (
        ListingTemplate(
            title="Supply of imaging equipment and eight-year service cover",
            summary=(
                "Two MRI and four CT systems across three hospitals, including installation, "
                "training and service."
            ),
            description=_body(
                "Supply, installation and long-term service of diagnostic imaging equipment.",
                "Site surveys and room preparation interfaces, delivery and installation, "
                "acceptance testing, applications training, and eight years of full-service "
                "cover with guaranteed uptime.",
            ),
            budget=(48_000_000, 62_000_000),
            duration_months=96,
            tags=("imaging", "MRI", "service cover"),
            min_years_experience=8,
            requires_bid_bond=True,
        ),
        ListingTemplate(
            title="Consumables framework for theatres and critical care",
            summary=(
                "Two-year call-off framework for single-use surgical and critical-care consumables."
            ),
            description=_body(
                "A framework for the supply of single-use consumables to operating theatres and "
                "critical care units.",
                "Scheduled and emergency supply, product substitution protocols, recall "
                "handling, consignment stock at two sites, and quarterly performance review.",
            ),
            budget=(19_000_000, 26_000_000),
            duration_months=24,
            tags=("consumables", "framework", "theatres"),
            min_years_experience=5,
        ),
    ),
    TenderCategory.EDUCATION_TRAINING: (
        ListingTemplate(
            title="Clinical skills training programme for nursing staff",
            summary=(
                "Simulation-based training for 900 nursing staff across three sites over two years."
            ),
            description=_body(
                "Delivery of a structured clinical skills programme using simulation.",
                "Curriculum design aligned to competency frameworks, simulation delivery, "
                "assessment and certification, train-the-trainer, and outcome reporting.",
            ),
            budget=(3_200_000, 4_800_000),
            duration_months=24,
            tags=("simulation", "CPD", "nursing"),
            min_years_experience=4,
        ),
    ),
    TenderCategory.TRANSPORT_LOGISTICS: (
        ListingTemplate(
            title="Depot logistics and parts distribution services",
            summary=(
                "Inbound receipt, storage and just-in-time distribution of vehicle parts across "
                "four depots."
            ),
            description=_body(
                "Operation of parts logistics supporting the Corporation's maintenance workshops.",
                "Goods receipt and inspection, warehouse management, kitting, just-in-time "
                "delivery to workshop bays, stock accuracy reporting, and returns handling.",
            ),
            budget=(13_000_000, 18_000_000),
            duration_months=48,
            tags=("warehousing", "JIT", "parts"),
            min_years_experience=5,
        ),
    ),
    TenderCategory.FLEET_VEHICLES: (
        ListingTemplate(
            title="Supply of 60 low-floor electric buses and charging",
            summary=(
                "Vehicle supply with depot charging infrastructure, telematics and a five-year "
                "battery warranty."
            ),
            description=_body(
                "Supply of battery-electric buses together with the depot infrastructure "
                "required to operate them.",
                "Vehicle manufacture to specification, depot charging design and installation, "
                "telematics integration, driver and technician training, and a five-year "
                "battery performance warranty.",
            ),
            budget=(180_000_000, 240_000_000),
            duration_months=30,
            tags=("electric bus", "charging", "telematics"),
            min_years_experience=10,
            requires_bid_bond=True,
        ),
    ),
    TenderCategory.SECURITY_SERVICES: (
        ListingTemplate(
            title="Manned guarding and control room services",
            summary=(
                "Licensed guarding across nine transport sites with a centrally staffed control "
                "room."
            ),
            description=_body(
                "Provision of manned guarding and monitoring across the Corporation's estate.",
                "Static and mobile guarding, access control, CCTV monitoring from a central "
                "control room, incident reporting, and coordination with public authorities.",
            ),
            budget=(14_500_000, 19_000_000),
            duration_months=36,
            tags=("guarding", "CCTV", "control room"),
            min_years_experience=5,
        ),
    ),
    TenderCategory.CATERING_HOSPITALITY: (
        ListingTemplate(
            title="Patient and staff catering across three hospitals",
            summary=(
                "Cook-fresh patient meals to therapeutic diets, plus staff restaurant and "
                "retail operation."
            ),
            description=_body(
                "Catering services covering patient feeding and staff hospitality.",
                "Menu development to therapeutic diet standards, meal production and ward "
                "distribution, allergen management, staff restaurant and retail operation, and "
                "food safety compliance.",
            ),
            budget=(22_000_000, 29_000_000),
            duration_months=48,
            tags=("patient catering", "therapeutic diets"),
            min_years_experience=5,
        ),
    ),
    TenderCategory.PRINTING_MEDIA: (
        ListingTemplate(
            title="Passenger information printing and installation",
            summary=(
                "Production and installation of timetable, wayfinding and safety material across "
                "the network."
            ),
            description=_body(
                "Production and installation of printed passenger information.",
                "Artwork adaptation, printing to durable specification, scheduled installation "
                "across stops and interchanges, and removal of superseded material.",
            ),
            budget=(1_600_000, 2_600_000),
            duration_months=24,
            tags=("wayfinding", "print", "installation"),
        ),
    ),
    TenderCategory.MARKETING_EVENTS: (
        ListingTemplate(
            title="Public awareness campaign for a new transport interchange",
            summary=(
                "Bilingual multi-channel campaign covering launch, wayfinding change and "
                "behaviour change messaging."
            ),
            description=_body(
                "A public awareness campaign supporting the opening of a major interchange.",
                "Strategy and creative development in Arabic and English, media planning and "
                "buying, on-street activation, community engagement, and campaign evaluation.",
            ),
            budget=(3_800_000, 5_600_000),
            duration_months=12,
            tags=("campaign", "bilingual", "behaviour change"),
            min_years_experience=4,
        ),
    ),
    TenderCategory.CONSULTING_ADVISORY: (
        ListingTemplate(
            title="Operating model review for shared corporate services",
            summary=(
                "Review of finance, HR and procurement operating models across eleven entities, "
                "with an implementation roadmap."
            ),
            description=_body(
                "An advisory engagement to review how corporate services are delivered across "
                "participating entities.",
                "Current-state assessment, benchmarking, target operating model design, "
                "business case, and a sequenced implementation roadmap with owner and cost per "
                "step.",
            ),
            budget=(4_200_000, 6_400_000),
            duration_months=10,
            tags=("operating model", "shared services"),
            min_years_experience=8,
        ),
    ),
    TenderCategory.LEGAL_SERVICES: (
        ListingTemplate(
            title="External legal counsel panel — commercial and construction",
            summary=(
                "Panel appointment for commercial contracting, construction disputes and "
                "regulatory advice."
            ),
            description=_body(
                "Appointment of a panel of firms to provide external legal advice on call-off "
                "terms.",
                "Commercial contract drafting and negotiation, construction and engineering "
                "disputes, regulatory and administrative law advice, and secondment support at "
                "agreed rates.",
            ),
            budget=(5_000_000, 8_000_000),
            duration_months=36,
            tags=("panel", "construction law"),
            min_years_experience=8,
        ),
    ),
    TenderCategory.FINANCIAL_AUDIT: (
        ListingTemplate(
            title="External audit services for the financial years ahead",
            summary=(
                "Statutory audit of eleven entities plus consolidated group reporting, over "
                "three financial years."
            ),
            description=_body(
                "Provision of external audit services across the participating entities.",
                "Statutory audit planning and execution, consolidation review, internal control "
                "observations, management letters, and attendance at audit committee.",
            ),
            budget=(4_600_000, 6_800_000),
            duration_months=36,
            tags=("statutory audit", "consolidation"),
            min_years_experience=10,
        ),
    ),
    TenderCategory.HR_RECRUITMENT: (
        ListingTemplate(
            title="Recruitment process outsourcing for technical roles",
            summary=(
                "Sourcing, screening and onboarding support for approximately 400 technical "
                "hires per year."
            ),
            description=_body(
                "Outsourced recruitment for hard-to-fill technical and engineering roles.",
                "Sourcing strategy, candidate screening against agreed criteria, assessment "
                "coordination, offer management, onboarding support, and quarterly reporting on "
                "time-to-hire and retention.",
            ),
            budget=(6_000_000, 9_500_000),
            duration_months=36,
            tags=("RPO", "technical hiring"),
            min_years_experience=5,
        ),
    ),
    TenderCategory.FURNITURE_FITOUT: (
        ListingTemplate(
            title="Interior fit-out and loose furniture for a civic headquarters",
            summary=(
                "Cat-B fit-out of 11,000 m² of workplace including joinery, partitions and "
                "loose furniture supply."
            ),
            description=_body(
                "Interior fit-out of a newly completed headquarters building.",
                "Partitions and ceilings, joinery, floor finishes, feature lighting, AV "
                "containment interfaces, loose furniture supply and installation, and snagging.",
            ),
            budget=(26_000_000, 34_000_000),
            duration_months=14,
            tags=("Cat-B", "workplace", "joinery"),
            min_years_experience=6,
            requires_bid_bond=True,
        ),
    ),
    TenderCategory.LABORATORY_SCIENTIFIC: (
        ListingTemplate(
            title="Supply and commissioning of a water quality laboratory",
            summary=(
                "Analytical instrumentation, LIMS integration and method validation for a new "
                "compliance laboratory."
            ),
            description=_body(
                "Equipping a new laboratory for regulatory water quality analysis.",
                "Supply and installation of chromatography, spectrometry and microbiology "
                "instrumentation, LIMS integration, method validation, accreditation support, "
                "and analyst training.",
            ),
            budget=(12_500_000, 17_000_000),
            duration_months=18,
            tags=("LIMS", "accreditation", "instrumentation"),
            min_years_experience=6,
        ),
    ),
    TenderCategory.DEFENCE_AEROSPACE: (
        ListingTemplate(
            title="Maintenance support for rotary-wing search and rescue fleet",
            summary=(
                "Scheduled and unscheduled maintenance, spares provisioning and airworthiness "
                "management."
            ),
            description=_body(
                "Maintenance and continuing airworthiness support for a search and rescue "
                "rotary-wing fleet.",
                "Scheduled inspections, unscheduled rectification, spares provisioning, "
                "component repair management, and continuing airworthiness records.",
            ),
            budget=(88_000_000, 115_000_000),
            duration_months=60,
            tags=("airworthiness", "rotary wing", "MRO"),
            min_years_experience=10,
            requires_bid_bond=True,
        ),
    ),
    TenderCategory.ENVIRONMENTAL_SERVICES: (
        ListingTemplate(
            title="Coastal habitat restoration and monitoring programme",
            summary=(
                "Mangrove replanting across 180 hectares with a five-year ecological monitoring "
                "commitment."
            ),
            description=_body(
                "Restoration of degraded coastal habitat, with measurable ecological outcomes.",
                "Baseline survey, propagation and planting, hydrological remediation, invasive "
                "species control, and five years of monitoring against agreed indicators.",
            ),
            budget=(8_800_000, 12_400_000),
            duration_months=60,
            tags=("mangrove", "restoration", "monitoring"),
            min_years_experience=5,
        ),
    ),
}

# --- Vendors --------------------------------------------------------------------------------

VENDORS: tuple[dict[str, object], ...] = (
    {
        "name": "Falcon Integrated Facilities",
        "description": (
            "Fictional mid-size FM and MEP contractor working across the northern emirates, "
            "with in-house maintenance, cleaning and small-works teams."
        ),
        "emirate": Emirate.SHARJAH.value,
        "city": "Sharjah",
        "industry": "Facilities management",
        "employee_count": 340,
        "year_established": 2009,
    },
    {
        "name": "Meridian Civil Contracting",
        "description": (
            "Fictional civil contractor delivering roads, drainage and structural remediation "
            "for public clients."
        ),
        "emirate": Emirate.ABU_DHABI.value,
        "city": "Abu Dhabi",
        "industry": "Civil engineering",
        "employee_count": 780,
        "year_established": 2003,
    },
    {
        "name": "Nimbus Digital Consulting",
        "description": (
            "Fictional technology consultancy specialising in public-sector digital services, "
            "cloud migration and data platforms."
        ),
        "emirate": Emirate.DUBAI.value,
        "city": "Dubai",
        "industry": "Technology consulting",
        "employee_count": 120,
        "year_established": 2014,
    },
)
