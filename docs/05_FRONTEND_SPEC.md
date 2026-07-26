# BidPilot UAE — Frontend Product and Design Specification

## 1. Stack

Recommended:

- React 19
- TypeScript strict mode
- Vite
- React Router
- TanStack Query
- React Hook Form + Zod
- Tailwind CSS or CSS Modules; choose one and remain consistent
- Motion for React for a few deliberate transitions
- Lucide React
- Vitest + Testing Library
- Playwright for the critical demo journey

Use the generated OpenAPI client or generated types.

## 2. Visual identity

**Concept:** The Procurement Ledger

A warm-white, editorial workspace that combines the authority of a legal dossier, the density of a tender compliance sheet, and the clarity of a financial terminal.

It should not look like a generic AI dashboard.

### Palette

```css
:root {
  --paper: #fbfaf5;
  --surface: #ffffff;
  --ink: #171714;
  --ink-muted: #66635c;
  --rule: #1d1d1a;
  --rule-soft: #d8d4c9;
  --signal: #b51f26;
  --signal-soft: #f7e8e8;
  --success: #1f6a4a;
  --warning: #9a6100;
  --danger: #a51d2d;
  --info: #1f506f;
}
```

White background does not mean empty or flat. Add atmosphere using:

- Fine paper grain.
- Hairline grid rules.
- Strong black dividers.
- Small editorial-red signals.
- Dense tables and asymmetric columns.

### Typography

Do not use Inter, Roboto, Arial, system UI, or Space Grotesk.

Recommended pairing:

- Display: `Newsreader` or `Cormorant Garamond`.
- UI/body: `IBM Plex Sans` or `Source Sans 3`.
- Data: `IBM Plex Mono`.

Choose one pair and centralize it.

### Geometry

- Radius: 0–4px.
- No soft floating-card shadows.
- Use visible borders.
- Use hard offset shadows only for selected hover states.
- Use 12-column asymmetric layouts.
- Preserve information density.

### Motion

- One staggered reveal when entering the dashboard.
- 140–220 ms mechanical transitions.
- Processing timeline stage changes.
- Citation panel slide-in.
- Respect reduced motion.

## 3. Global shell

Desktop:

- Narrow left navigation rail.
- Top utility strip.
- Main 12-column workspace.
- Optional right source panel.

Mobile:

- Collapsed navigation.
- Single-column content.
- Bottom sheet or full-screen source viewer.
- Minimum 44px interactive targets.

## 4. Pages

### Authentication

- Sign in.
- Register.
- Optional reset password.

### Tender desk

Show tenders in a dense ledger/table:

- Tender title.
- Buyer.
- Deadline.
- Analysis status.
- Decision label.
- Readiness score.
- Last updated.

Include:

- Search.
- Status filter.
- Deadline filter.
- Strong empty state leading to first upload.

### Company profile

Sections:

- Identity and licence.
- Services.
- Certifications.
- Project experience.
- Capacity and preferences.
- Evidence items.

### New tender

- Tender metadata.
- Drag-and-drop PDF upload.
- File validation messages.
- Clear statement that AI output is advisory.

### Processing room

Display real stages returned by the backend. Do not fake percentages.

Example:

```text
01 File validated
02 Text extracted
03 38 requirements identified
04 Citations verified
05 Company evidence compared
06 Readiness calculated
```

For active stage, show a restrained animated rule or scanning indicator.

### Tender command center

Top area:

- Tender title and reference.
- Buyer.
- Deadline.
- Decision stamp.
- Readiness score.
- Analysis version.

Main asymmetric layout:

- Left 8 columns: blockers, evidence gaps, next actions, dimension scores.
- Right 4 columns: tender metadata, processing facts, token cost, export.

### Compliance matrix

Columns:

- ID.
- Requirement.
- Category.
- Obligation.
- Match status.
- Confidence.
- Source page.
- Review state.

Interactions:

- Filter.
- Sort.
- Row opens citation panel.
- Inline human status override.
- Reason required when changing machine status.
- Keyboard navigation.

### Source viewer

Show:

- Document name.
- Page number.
- Exact quote.
- Verification status.
- Page text or rendered page image.
- Highlighted cited passage when technically feasible.

### Risk register

Use a serious list/table, not decorative charts.

- Severity mark.
- Risk type.
- Clause summary.
- Why it matters.
- Suggested review.
- Citation.

### Readiness report

- Overall score.
- Decision label.
- Hard blockers.
- Six dimension rows.
- Assumptions.
- Human override.
- Export.

### Settings/about project

For portfolio value, include an “Engineering notes” page explaining:

- Model/provider.
- Prompt version.
- Citation method.
- Deterministic scoring.
- Limitations.

Do not expose secrets or internal prompts containing user content.

## 5. Reusable components

- `AppShell`
- `EditorialPageHeader`
- `LedgerTable`
- `DecisionStamp`
- `ReadinessDial` or linear meter
- `DimensionScoreRow`
- `BlockerNotice`
- `ProcessingTimeline`
- `UploadDossier`
- `RequirementStatusSelect`
- `CitationButton`
- `SourceDrawer`
- `RiskMark`
- `EvidenceBadge`
- `ProblemDetailsAlert`
- `EmptyLedgerState`
- `HumanReviewPanel`

Avoid wrapper components with no behavior or visual meaning.

## 6. State management

- TanStack Query owns remote state.
- Local component state for filters, drawers, and forms.
- Avoid global stores unless authentication or a truly shared UI concern needs one.
- Centralize API errors and token refresh.
- Use optimistic updates only for safe review actions; roll back visibly on failure.

## 7. Accessibility

- WCAG 2.2 AA target.
- Visible focus states.
- Semantic headings and landmarks.
- Buttons for actions; anchors for navigation.
- Table headers and accessible labels.
- Color never acts as the only status signal.
- Reduced-motion support.
- Error summary for forms.

## 8. Frontend completion criteria

- No mocked data in the final demo path.
- All major loading, empty, error, and success states implemented.
- Responsive at mobile, tablet, and desktop widths.
- Playwright test covers login → upload → processing → report.
- No provider API key in frontend source or network traffic.
