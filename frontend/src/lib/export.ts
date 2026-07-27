/** Client-side export of already-loaded analysis data. Server-side export endpoints (with
 *  signed downloads) arrive in Phase 11; this exports what the command center has in hand. */

function download(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function csvCell(value: unknown): string {
  const s = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export interface ExportRequirement {
  category: string;
  obligation: string;
  normalized_text: string;
  machine_status: string;
  reviewed_status: string;
  citation_verified: boolean;
  citations: { page_number: number; verified: boolean }[];
}

export function exportRequirementsCsv(requirements: ExportRequirement[], ref: string): void {
  const header = [
    "category",
    "obligation",
    "requirement",
    "machine_status",
    "reviewed_status",
    "citation_verified",
    "source_pages",
  ];
  const rows = requirements.map((r) =>
    [
      r.category,
      r.obligation,
      r.normalized_text,
      r.machine_status,
      r.reviewed_status,
      r.citation_verified,
      r.citations.map((c) => c.page_number).join(" "),
    ]
      .map(csvCell)
      .join(","),
  );
  download(`${ref}-requirements.csv`, [header.join(","), ...rows].join("\n"), "text/csv");
}

export function exportAnalysisJson(payload: unknown, ref: string): void {
  download(`${ref}-analysis.json`, JSON.stringify(payload, null, 2), "application/json");
}
