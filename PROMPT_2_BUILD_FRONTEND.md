# Claude Code Master Prompt — Build the BidPilot Frontend

You are the lead frontend engineer and product designer for BidPilot UAE.

Build a polished portfolio-grade frontend against the completed backend. The interface must feel credible in a technical interview and clear during a live product demonstration. It is not an enterprise design-system exercise.

## Read first

- `@docs/00_START_HERE.md`
- `@docs/01_PRODUCT_REQUIREMENTS.md`
- `@docs/04_API_AND_DATA_MODEL.md`
- `@docs/05_FRONTEND_SPEC.md`
- `@docs/07_TEST_DEMO_DEPLOYMENT.md`
- `@CLAUDE.md`
- backend `@artifacts/openapi.json`

Inspect the current frontend and backend contracts before editing.

## Required stack

Use:

- React 19+
- TypeScript strict mode
- Vite
- React Router
- TanStack Query
- React Hook Form + Zod
- Tailwind CSS or CSS Modules; choose one coherent system
- Motion for React for a few deliberate interactions
- Lucide React
- Vitest + Testing Library
- Playwright
- MSW for tests

Generate or consume TypeScript API types from OpenAPI. Do not maintain a second handwritten contract.

## Product requirement

Implement the complete real demo journey:

1. Register or sign in.
2. View/edit company profile and evidence.
3. Create a tender.
4. Upload a PDF.
5. Observe real processing stages.
6. Open the tender command center.
7. Review the compliance matrix.
8. Open a citation and inspect its source.
9. Review risk findings.
10. Understand the decomposed readiness score.
11. Override one machine finding with a reason.
12. Export the result.

Do not ship the final path with mocked data.

## Aesthetic direction

Create a permanent light interface called **The Procurement Ledger**.

The design should combine:

- Warm white paper.
- Ink-black structural rules.
- Sparse editorial red.
- Serious serif display typography.
- Dense but legible compliance tables.
- Asymmetric editorial grids.
- Sharp corners.
- Mechanical motion.

Avoid generic AI/SaaS styling:

- No purple gradients.
- No glassmorphism.
- No floating pastel cards.
- No excessive rounded corners.
- No Inter, Roboto, Arial, default system fonts, or Space Grotesk.
- No meaningless dashboard charts.
- No giant empty hero inside the authenticated app.

Choose a coherent font pairing such as:

- Newsreader + IBM Plex Sans + IBM Plex Mono, or
- Cormorant Garamond + Source Sans 3 + IBM Plex Mono.

Centralize tokens with CSS variables.

Use the palette and rules in `@docs/05_FRONTEND_SPEC.md`.

## Motion

- One orchestrated staggered reveal on dashboard entry.
- 140–220 ms transitions.
- Animate transform and opacity.
- Processing stages transition visibly.
- Citation panel enters from the right on desktop.
- Respect `prefers-reduced-motion`.

## Required pages

- Sign in and register.
- Tender desk.
- Company profile and evidence.
- New tender/upload.
- Processing room.
- Tender command center.
- Compliance matrix.
- Source viewer.
- Risk register.
- Readiness report.
- Engineering notes/about.

## Required states

For every data surface, implement:

- Loading.
- Empty.
- Error.
- Success.
- Permission/session expired where relevant.

Never show fake progress percentages. Display backend stages and messages.

## API and state rules

- TanStack Query owns server state.
- Keep UI state local unless genuinely shared.
- Centralize access-token refresh behavior.
- Never store provider keys.
- Do not store refresh tokens in localStorage.
- Display RFC 7807 errors meaningfully.
- Surface failed analyses with retry actions.
- Show version conflicts safely if implemented.

## Accessibility

- WCAG 2.2 AA target.
- Semantic landmarks and headings.
- Keyboard-accessible matrix.
- Visible focus.
- Minimum 44px touch targets on mobile.
- Status conveyed by text/icon, not color alone.
- Reduced motion.
- Proper table headers and accessible dialogs.

## Testing

Add:

- Component tests for decision stamp, status override, error alert, and processing timeline.
- MSW tests for loading/error/success.
- Playwright journey from login to completed report using seeded backend data.
- Responsive checks for mobile and desktop.

## Completion standard

Before declaring completion:

- Run formatting, linting, type checks, unit tests, and Playwright.
- Fix failures.
- Verify the live API path.
- Confirm no secret exists in frontend code or built assets.
- Update README with screenshots and frontend setup.

Finish with exact commands run, results, known limitations, and a page checklist.
