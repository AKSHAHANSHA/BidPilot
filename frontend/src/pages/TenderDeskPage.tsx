import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, Spinner } from "../components/ui";

interface TenderRow {
  id: string;
  title: string;
  buyer: string | null;
  submission_deadline: string | null;
  status: string;
  document_count: number;
  updated_at: string;
}

export function TenderDeskPage() {
  const [search, setSearch] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["tenders"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/tenders", { params: { query: { limit: 100 } } });
      if (error) throw error;
      return data;
    },
  });

  const items = ((data?.items ?? []) as TenderRow[]).filter(
    (t) =>
      !search ||
      t.title.toLowerCase().includes(search.toLowerCase()) ||
      (t.buyer ?? "").toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div>
      <header className="flex items-end justify-between mb-6 border-b-2 border-rule pb-3">
        <div>
          <h1 className="font-display text-3xl">Tender Desk</h1>
          <p className="text-sm text-ink-muted">Every tender you are reviewing.</p>
        </div>
        <input
          placeholder="Search title or buyer…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border border-rule-soft bg-surface px-3 py-2 text-sm rounded-[3px] w-64 max-sm:w-40"
        />
      </header>

      {isLoading ? (
        <Spinner label="Loading tenders…" />
      ) : items.length === 0 ? (
        <Card className="p-10 text-center">
          <p className="font-display text-xl mb-2">No tenders yet</p>
          <p className="text-sm text-ink-muted mb-4">
            Upload your first tender PDF to see extracted requirements, risks, and a readiness score.
          </p>
          <Link to="/tenders/new" className="text-signal underline text-sm">
            Create your first tender →
          </Link>
        </Card>
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-rule text-left text-xs uppercase tracking-wide text-ink-muted">
                <th className="px-4 py-3 font-semibold">Tender</th>
                <th className="px-4 py-3 font-semibold">Buyer</th>
                <th className="px-4 py-3 font-semibold">Deadline</th>
                <th className="px-4 py-3 font-semibold">Docs</th>
                <th className="px-4 py-3 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id} className="border-b border-rule-soft hover:bg-paper">
                  <td className="px-4 py-3">
                    <Link to={`/tenders/${t.id}`} className="font-medium hover:text-signal">
                      {t.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-ink-muted">{t.buyer ?? "—"}</td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {t.submission_deadline
                      ? new Date(t.submission_deadline).toLocaleDateString()
                      : "—"}
                  </td>
                  <td className="px-4 py-3 font-mono">{t.document_count}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs uppercase tracking-wide text-ink-muted">
                      {t.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
