# BidPilot UAE — Start Here

**Project type:** Production-minded personal portfolio application  
**Purpose:** Academic submission, technical portfolio, interviews, and controlled live demonstrations  
**Primary developer:** One person using Claude Code  
**Initial vertical:** UAE facilities-management SMEs  
**Backend priority:** Reliability, explainability, clean architecture, and demo readiness  
**Not the goal:** Enterprise SaaS infrastructure or large-scale commercial operations

## Product statement

BidPilot UAE helps a small business review a tender before committing days of work. A user uploads a tender PDF and creates a company profile. The application extracts tender requirements, identifies eligibility gaps and risky clauses, compares requirements against company evidence, calculates a transparent bid-readiness score, and produces a cited advisory recommendation.

> Know whether to bid before spending days preparing.

## What “strong backend” means here

A strong backend is not the backend with the most infrastructure. It is the backend that is:

- Correct and explainable.
- Modular and testable.
- Secure enough for a public portfolio demo.
- Reliable when model output is malformed or a document is difficult.
- Easy to run locally and deploy cheaply.
- Clear enough to defend in a technical interview.
- Designed so a future commercial version could evolve without rewriting everything.

## Required documents

Read these in order:

1. `01_PRODUCT_REQUIREMENTS.md`
2. `02_BACKEND_ARCHITECTURE.md`
3. `03_AI_PIPELINE_AND_SCORING.md`
4. `04_API_AND_DATA_MODEL.md`
5. `05_FRONTEND_SPEC.md`
6. `06_IMPLEMENTATION_ROADMAP.md`
7. `07_TEST_DEMO_DEPLOYMENT.md`
8. `CLAUDE.md`

Then run Claude Code using:

- `PROMPT_1_BUILD_BACKEND.md`
- `PROMPT_2_BUILD_FRONTEND.md`

## Recommended repository

```text
bidpilot/
├── docs/
│   ├── 00_START_HERE.md
│   ├── 01_PRODUCT_REQUIREMENTS.md
│   ├── 02_BACKEND_ARCHITECTURE.md
│   ├── 03_AI_PIPELINE_AND_SCORING.md
│   ├── 04_API_AND_DATA_MODEL.md
│   ├── 05_FRONTEND_SPEC.md
│   ├── 06_IMPLEMENTATION_ROADMAP.md
│   └── 07_TEST_DEMO_DEPLOYMENT.md
├── backend/
├── frontend/
├── CLAUDE.md
├── PROMPT_1_BUILD_BACKEND.md
├── PROMPT_2_BUILD_FRONTEND.md
└── README.md
```

## Build strategy

Build a vertical slice before adding breadth:

1. Create a company profile.
2. Upload one text-based tender PDF.
3. Extract page-aware text.
4. Extract cited requirements.
5. Validate citations.
6. Match requirements to company facts.
7. Calculate deterministic readiness.
8. Display the report in a minimal frontend.
9. Add OCR, authentication, exports, and visual polish afterward.

A complete narrow workflow is more impressive than twenty incomplete features.
