import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { toFieldErrors } from "../lib/errors";
import { PROJECT_STATUSES, humanize } from "../lib/vocab";
import { Button, Field, ProblemAlert, Select, TextArea } from "./ui";
import { Modal } from "./Modal";

export interface ProjectValues {
  id?: string;
  client_name: string;
  project_title: string;
  industry: string;
  description: string;
  contract_value: string;
  currency: string;
  start_date: string;
  end_date: string;
  status: string;
  location: string;
  services_delivered: string;
  outcome: string;
  client_reference_available: boolean;
  is_confidential: boolean;
}

const EMPTY: ProjectValues = {
  client_name: "",
  project_title: "",
  industry: "",
  description: "",
  contract_value: "",
  currency: "AED",
  start_date: "",
  end_date: "",
  status: "completed",
  location: "",
  services_delivered: "",
  outcome: "",
  client_reference_available: false,
  is_confidential: false,
};

/** Create or edit a company project. A completed project requires an end date; the backend
 *  enforces this and its message is surfaced inline. */
export function ProjectForm({
  initial,
  onClose,
}: {
  initial?: Partial<ProjectValues>;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<ProjectValues>({ ...EMPTY, ...initial });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const isEdit = Boolean(initial?.id);

  const set = <K extends keyof ProjectValues>(key: K) => (v: ProjectValues[K]) =>
    setValues((prev) => ({ ...prev, [key]: v }));

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        client_name: values.client_name,
        project_title: values.project_title,
        industry: values.industry,
        description: values.description,
        contract_value: values.contract_value || null,
        currency: values.currency || "AED",
        start_date: values.start_date,
        end_date: values.status === "completed" ? values.end_date || null : null,
        status: values.status as never,
        location: values.location,
        services_delivered: values.services_delivered
          ? values.services_delivered.split(",").map((s) => s.trim()).filter(Boolean)
          : [],
        outcome: values.outcome || null,
        client_reference_available: values.client_reference_available,
        is_confidential: values.is_confidential,
      };
      const result = isEdit
        ? await api.PATCH("/api/v1/company/projects/{project_id}", {
            params: { path: { project_id: initial!.id! } },
            body,
          })
        : await api.POST("/api/v1/company/projects", { body });
      if (result.error) throw result.error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
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
    <Modal title={isEdit ? "Edit project" : "Add project"} onClose={onClose} wide>
      <form onSubmit={submit} className="space-y-4">
        {formError ? <ProblemAlert message={formError} /> : null}
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Client name" value={values.client_name} onChange={(e) => set("client_name")(e.target.value)} required error={fieldErrors.client_name} />
          <Field label="Project title" value={values.project_title} onChange={(e) => set("project_title")(e.target.value)} required error={fieldErrors.project_title} />
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Industry" value={values.industry} onChange={(e) => set("industry")(e.target.value)} required error={fieldErrors.industry} />
          <Field label="Location" value={values.location} onChange={(e) => set("location")(e.target.value)} required error={fieldErrors.location} />
        </div>
        <TextArea label="Description" value={values.description} onChange={(e) => set("description")(e.target.value)} rows={3} required error={fieldErrors.description} />
        <div className="grid sm:grid-cols-3 gap-4">
          <Select label="Status" value={values.status} onChange={(e) => set("status")(e.target.value)} error={fieldErrors.status}>
            {PROJECT_STATUSES.map((s) => (
              <option key={s} value={s}>{humanize(s)}</option>
            ))}
          </Select>
          <Field label="Start date" type="date" value={values.start_date} onChange={(e) => set("start_date")(e.target.value)} required error={fieldErrors.start_date} />
          <Field label="End date" type="date" value={values.end_date} onChange={(e) => set("end_date")(e.target.value)} disabled={values.status === "current"} error={fieldErrors.end_date} />
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Contract value (optional)" type="number" value={values.contract_value} onChange={(e) => set("contract_value")(e.target.value)} error={fieldErrors.contract_value} />
          <Field label="Currency" value={values.currency} onChange={(e) => set("currency")(e.target.value.toUpperCase())} maxLength={3} error={fieldErrors.currency} />
        </div>
        <Field label="Services delivered (comma-separated)" value={values.services_delivered} onChange={(e) => set("services_delivered")(e.target.value)} required error={fieldErrors.services_delivered} />
        <TextArea label="Outcome (optional)" value={values.outcome} onChange={(e) => set("outcome")(e.target.value)} rows={2} error={fieldErrors.outcome} />
        <div className="flex gap-6 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={values.client_reference_available} onChange={(e) => set("client_reference_available")(e.target.checked)} />
            Client reference available
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={values.is_confidential} onChange={(e) => set("is_confidential")(e.target.checked)} />
            Confidential
          </label>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save project"}</Button>
        </div>
      </form>
    </Modal>
  );
}
