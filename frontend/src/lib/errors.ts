import type { ProblemDetail } from "../api/client";

/**
 * Map an RFC 7807 problem detail into a per-field error map plus a top-level message.
 *
 * The backend returns validation failures as `errors: [{ field: "body.title", message }]`.
 * The `body.` / `query.` prefix is stripped so the map keys match form field names. Anything
 * without a field lands in `_form`, shown as a banner.
 */
export interface FieldErrors {
  fields: Record<string, string>;
  form: string | null;
}

export function toFieldErrors(error: unknown): FieldErrors {
  const problem = error as Partial<ProblemDetail> | undefined;
  const fields: Record<string, string> = {};
  for (const item of problem?.errors ?? []) {
    const key = item.field.replace(/^(body|query|path)\./, "");
    if (!(key in fields)) fields[key] = item.message;
  }
  const form =
    problem?.errors && problem.errors.length
      ? null // field-level errors are shown inline; no duplicate banner
      : (problem?.detail ?? problem?.title ?? "Something went wrong.");
  return { fields, form };
}
