import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  createCompanyProject,
  fetchCategories,
  type CategoryDto,
} from "../lib/marketplace";
import { Button, Card, Field, ProblemAlert, Select, TextArea } from "../components/ui";

export function CompanyNewProjectPage() {
  const navigate = useNavigate();
  const [categories, setCategories] = useState<CategoryDto[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    title: "",
    description: "",
    category: "",
    location: "Dubai",
    budget_aed: "",
    submission_deadline: "",
    cover_image_url: "",
    requirements_summary: "",
  });

  useEffect(() => {
    fetchCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  function update<K extends keyof typeof form>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await createCompanyProject({
        title: form.title,
        description: form.description,
        category: form.category,
        location: form.location || null,
        budget_aed: form.budget_aed ? Number(form.budget_aed) : null,
        submission_deadline: form.submission_deadline
          ? new Date(form.submission_deadline).toISOString()
          : null,
        cover_image_url: form.cover_image_url || null,
        requirements_summary: form.requirements_summary || null,
        is_public: true,
      });
      navigate(`/projects/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the project");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <h1 className="font-display text-4xl mb-2">Post a new project</h1>
      <p className="text-sm text-ink-muted mb-6">
        Vendors will see this on the public marketplace immediately.
      </p>
      <Card className="p-6">
        <form onSubmit={submit} className="space-y-4">
          {error ? <ProblemAlert message={error} /> : null}
          <Field
            label="Title"
            value={form.title}
            onChange={(e) => update("title", e.target.value)}
            required
            minLength={3}
            maxLength={255}
          />
          <TextArea
            label="Description"
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
            required
            minLength={20}
            rows={5}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Select
              label="Category"
              value={form.category}
              onChange={(e) => update("category", e.target.value)}
              required
            >
              <option value="">Select a category</option>
              {categories.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.label}
                </option>
              ))}
            </Select>
            <Field
              label="Location"
              value={form.location}
              onChange={(e) => update("location", e.target.value)}
              maxLength={120}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field
              label="Budget (AED)"
              type="number"
              min={0}
              value={form.budget_aed}
              onChange={(e) => update("budget_aed", e.target.value)}
            />
            <Field
              label="Submission deadline"
              type="datetime-local"
              value={form.submission_deadline}
              onChange={(e) => update("submission_deadline", e.target.value)}
            />
          </div>
          <Field
            label="Cover image URL"
            value={form.cover_image_url}
            onChange={(e) => update("cover_image_url", e.target.value)}
            placeholder="https://…"
          />
          <TextArea
            label="Requirements summary"
            value={form.requirements_summary}
            onChange={(e) => update("requirements_summary", e.target.value)}
            rows={5}
            placeholder="One requirement per line. The AI screener will use this to score applicants."
          />
          <div className="flex justify-end gap-3">
            <Button variant="ghost" type="button" onClick={() => navigate(-1)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Publishing…" : "Publish project"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
