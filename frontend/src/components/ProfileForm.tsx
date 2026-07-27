import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { toFieldErrors } from "../lib/errors";
import { EMIRATES, REVENUE_RANGES, humanize } from "../lib/vocab";
import { Button, Field, ProblemAlert, Select, TextArea } from "./ui";
import { Modal } from "./Modal";

export interface ProfileValues {
  legal_name: string;
  trading_name: string;
  description: string;
  industry: string;
  emirate: string;
  country: string;
  year_established: string;
  employee_count: string;
  years_of_experience: string;
  trade_licence_number: string;
  trade_licence_expiry: string;
  licence_activities: string;
  website: string;
  contact_email: string;
  contact_phone: string;
  annual_revenue_range: string;
  preferred_contract_value_min: string;
  preferred_contract_value_max: string;
  service_categories: string;
  geographic_coverage: string;
}

/** Create or edit the single company profile. `mode` decides POST vs PATCH. Only changed and
 *  non-empty fields matter; the backend validates and its messages are shown inline. */
export function ProfileForm({
  initial,
  mode,
  onClose,
}: {
  initial: Partial<ProfileValues>;
  mode: "create" | "edit";
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [v, setV] = useState<ProfileValues>({
    legal_name: "",
    trading_name: "",
    description: "",
    industry: "",
    emirate: "dubai",
    country: "United Arab Emirates",
    year_established: "",
    employee_count: "",
    years_of_experience: "",
    trade_licence_number: "",
    trade_licence_expiry: "",
    licence_activities: "",
    website: "",
    contact_email: "",
    contact_phone: "",
    annual_revenue_range: "",
    preferred_contract_value_min: "",
    preferred_contract_value_max: "",
    service_categories: "",
    geographic_coverage: "",
    ...initial,
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const set = (key: keyof ProfileValues) => (val: string) =>
    setV((prev) => ({ ...prev, [key]: val }));

  const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        legal_name: v.legal_name,
        trading_name: v.trading_name || null,
        description: v.description,
        industry: v.industry,
        emirate: v.emirate as never,
        country: v.country,
        year_established: Number(v.year_established),
        employee_count: Number(v.employee_count),
        years_of_experience: Number(v.years_of_experience),
        trade_licence_number: v.trade_licence_number,
        trade_licence_expiry: v.trade_licence_expiry,
        licence_activities: csv(v.licence_activities),
        website: v.website || null,
        contact_email: v.contact_email,
        contact_phone: v.contact_phone || null,
        annual_revenue_range: (v.annual_revenue_range || null) as never,
        preferred_contract_value_min: v.preferred_contract_value_min || null,
        preferred_contract_value_max: v.preferred_contract_value_max || null,
        service_categories: csv(v.service_categories),
        geographic_coverage: csv(v.geographic_coverage),
      };
      const result =
        mode === "create"
          ? await api.POST("/api/v1/company", { body })
          : await api.PATCH("/api/v1/company", { body });
      if (result.error) throw result.error;
    },
    onSuccess: () => {
      // Refreshes both the profile and its completion score.
      queryClient.invalidateQueries({ queryKey: ["company"] });
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
    <Modal title={mode === "create" ? "Create company profile" : "Edit company profile"} onClose={onClose} wide>
      <form onSubmit={submit} className="space-y-4">
        {formError ? <ProblemAlert message={formError} /> : null}
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Legal name" value={v.legal_name} onChange={(e) => set("legal_name")(e.target.value)} required error={fieldErrors.legal_name} />
          <Field label="Trading name (optional)" value={v.trading_name} onChange={(e) => set("trading_name")(e.target.value)} error={fieldErrors.trading_name} />
        </div>
        <TextArea label="Description" value={v.description} onChange={(e) => set("description")(e.target.value)} rows={3} required error={fieldErrors.description} />
        <div className="grid sm:grid-cols-3 gap-4">
          <Field label="Industry" value={v.industry} onChange={(e) => set("industry")(e.target.value)} required error={fieldErrors.industry} />
          <Select label="Emirate" value={v.emirate} onChange={(e) => set("emirate")(e.target.value)} error={fieldErrors.emirate}>
            {EMIRATES.map((em) => (<option key={em} value={em}>{humanize(em)}</option>))}
          </Select>
          <Field label="Country" value={v.country} onChange={(e) => set("country")(e.target.value)} required error={fieldErrors.country} />
        </div>
        <div className="grid sm:grid-cols-3 gap-4">
          <Field label="Year established" type="number" value={v.year_established} onChange={(e) => set("year_established")(e.target.value)} required error={fieldErrors.year_established} />
          <Field label="Employees" type="number" value={v.employee_count} onChange={(e) => set("employee_count")(e.target.value)} required error={fieldErrors.employee_count} />
          <Field label="Years of experience" type="number" value={v.years_of_experience} onChange={(e) => set("years_of_experience")(e.target.value)} required error={fieldErrors.years_of_experience} />
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Trade licence number" value={v.trade_licence_number} onChange={(e) => set("trade_licence_number")(e.target.value)} required error={fieldErrors.trade_licence_number} />
          <Field label="Trade licence expiry" type="date" value={v.trade_licence_expiry} onChange={(e) => set("trade_licence_expiry")(e.target.value)} required error={fieldErrors.trade_licence_expiry} />
        </div>
        <Field label="Licence activities (comma-separated)" value={v.licence_activities} onChange={(e) => set("licence_activities")(e.target.value)} required error={fieldErrors.licence_activities} />
        <div className="grid sm:grid-cols-3 gap-4">
          <Field label="Contact email" type="email" value={v.contact_email} onChange={(e) => set("contact_email")(e.target.value)} required error={fieldErrors.contact_email} />
          <Field label="Contact phone (optional)" value={v.contact_phone} onChange={(e) => set("contact_phone")(e.target.value)} error={fieldErrors.contact_phone} />
          <Field label="Website (optional)" value={v.website} onChange={(e) => set("website")(e.target.value)} error={fieldErrors.website} />
        </div>
        <div className="grid sm:grid-cols-3 gap-4">
          <Select label="Revenue range (optional)" value={v.annual_revenue_range} onChange={(e) => set("annual_revenue_range")(e.target.value)} error={fieldErrors.annual_revenue_range}>
            <option value="">—</option>
            {REVENUE_RANGES.map((r) => (<option key={r} value={r}>{humanize(r)}</option>))}
          </Select>
          <Field label="Preferred min (AED)" type="number" value={v.preferred_contract_value_min} onChange={(e) => set("preferred_contract_value_min")(e.target.value)} error={fieldErrors.preferred_contract_value_min} />
          <Field label="Preferred max (AED)" type="number" value={v.preferred_contract_value_max} onChange={(e) => set("preferred_contract_value_max")(e.target.value)} error={fieldErrors.preferred_contract_value_max} />
        </div>
        <Field label="Service categories (comma-separated)" value={v.service_categories} onChange={(e) => set("service_categories")(e.target.value)} required error={fieldErrors.service_categories} />
        <Field label="Geographic coverage (comma-separated)" value={v.geographic_coverage} onChange={(e) => set("geographic_coverage")(e.target.value)} required error={fieldErrors.geographic_coverage} />
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save profile"}</Button>
        </div>
      </form>
    </Modal>
  );
}
