import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { toFieldErrors } from "../lib/errors";
import { EVIDENCE_CATEGORIES, VERIFICATION_STATUSES, humanize } from "../lib/vocab";
import { Button, Field, ProblemAlert, Select, TextArea } from "./ui";
import { Modal } from "./Modal";

export interface EvidenceValues {
  id?: string;
  title: string;
  category: string;
  issuing_organisation: string;
  reference_number: string;
  description: string;
  issue_date: string;
  expiry_date: string;
  verification_status: string;
  tags: string;
}

const EMPTY: EvidenceValues = {
  title: "",
  category: "certification",
  issuing_organisation: "",
  reference_number: "",
  description: "",
  issue_date: "",
  expiry_date: "",
  verification_status: "unverified",
  tags: "",
};

/** Create or edit a company evidence item. `initial.id` present ⇒ edit (PATCH), else create. */
export function EvidenceForm({
  initial,
  onClose,
}: {
  initial?: Partial<EvidenceValues>;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<EvidenceValues>({ ...EMPTY, ...initial });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const isEdit = Boolean(initial?.id);

  const set = (key: keyof EvidenceValues) => (v: string) =>
    setValues((prev) => ({ ...prev, [key]: v }));

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        title: values.title,
        category: values.category as never,
        issuing_organisation: values.issuing_organisation || null,
        reference_number: values.reference_number || null,
        description: values.description,
        issue_date: values.issue_date || null,
        expiry_date: values.expiry_date || null,
        verification_status: values.verification_status as never,
        tags: values.tags
          ? values.tags.split(",").map((t) => t.trim()).filter(Boolean)
          : [],
      };
      const result = isEdit
        ? await api.PATCH("/api/v1/company/evidence/{evidence_id}", {
            params: { path: { evidence_id: initial!.id! } },
            body,
          })
        : await api.POST("/api/v1/company/evidence", { body });
      if (result.error) throw result.error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evidence"] });
      onClose();
    },
    onError: (error) => {
      const mapped = toFieldErrors(error);
      setFieldErrors(mapped.fields);
      setFormError(mapped.form);
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    setFieldErrors({});
    setFormError(null);
    save.mutate();
  }

  return (
    <Modal title={isEdit ? "Edit evidence" : "Add evidence"} onClose={onClose} wide>
      <form onSubmit={submit} className="space-y-4">
        {formError ? <ProblemAlert message={formError} /> : null}
        <Field label="Title" value={values.title} onChange={(e) => set("title")(e.target.value)} required error={fieldErrors.title} />
        <div className="grid sm:grid-cols-2 gap-4">
          <Select label="Category" value={values.category} onChange={(e) => set("category")(e.target.value)} error={fieldErrors.category}>
            {EVIDENCE_CATEGORIES.map((c) => (
              <option key={c} value={c}>{humanize(c)}</option>
            ))}
          </Select>
          <Select label="Verification status" value={values.verification_status} onChange={(e) => set("verification_status")(e.target.value)} error={fieldErrors.verification_status}>
            {VERIFICATION_STATUSES.map((s) => (
              <option key={s} value={s}>{humanize(s)}</option>
            ))}
          </Select>
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Issuing organisation (optional)" value={values.issuing_organisation} onChange={(e) => set("issuing_organisation")(e.target.value)} error={fieldErrors.issuing_organisation} />
          <Field label="Reference number (optional)" value={values.reference_number} onChange={(e) => set("reference_number")(e.target.value)} error={fieldErrors.reference_number} />
        </div>
        <TextArea label="Description" value={values.description} onChange={(e) => set("description")(e.target.value)} rows={3} required error={fieldErrors.description} />
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Issue date (optional)" type="date" value={values.issue_date} onChange={(e) => set("issue_date")(e.target.value)} error={fieldErrors.issue_date} />
          <Field label="Expiry date (optional)" type="date" value={values.expiry_date} onChange={(e) => set("expiry_date")(e.target.value)} error={fieldErrors.expiry_date} />
        </div>
        <Field label="Tags (comma-separated)" value={values.tags} onChange={(e) => set("tags")(e.target.value)} error={fieldErrors.tags} />
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save evidence"}</Button>
        </div>
      </form>
    </Modal>
  );
}
