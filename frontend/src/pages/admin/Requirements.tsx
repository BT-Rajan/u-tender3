import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { DocumentRequirement } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { QueryError } from "@/components/QueryError";
import { useI18n } from "@/i18n/I18nContext";

const INPUT =
  "w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20";

export function AdminRequirementsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isRequired, setIsRequired] = useState(true);
  const [scopeFilter, setScopeFilter] = useState<"contractor" | "owner">("contractor");
  const [error, setError] = useState<string | null>(null);

  const {
    data: requirements,
    isError: requirementsError,
    refetch: refetchRequirements,
  } = useQuery({
    queryKey: ["admin-requirements"],
    queryFn: () => apiFetch<DocumentRequirement[]>("/admin/requirements"),
  });

  const invalidate = () => {
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["admin-requirements"] });
  };
  const onMutationError = (err: unknown, fallback: string) =>
    setError(err instanceof ApiError ? err.detail : fallback);

  const addMutation = useMutation({
    mutationFn: () =>
      apiFetch("/admin/requirements", {
        method: "POST",
        body: { name, description: description || null, is_required: isRequired, applies_to: scopeFilter },
      }),
    onSuccess: () => {
      setName("");
      setDescription("");
      setIsRequired(true);
      invalidate();
    },
    onError: (err) => onMutationError(err, t("admin.requirements.addError")),
  });

  const toggleRequiredMutation = useMutation({
    mutationFn: ({ id, value }: { id: string; value: boolean }) =>
      apiFetch(`/admin/requirements/${id}`, { method: "PATCH", body: { is_required: value } }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, t("admin.requirements.updateError")),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => apiFetch(`/admin/requirements/${id}`, { method: "PATCH", body: { is_active: false } }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, t("admin.requirements.removeError")),
  });

  const active = (requirements ?? []).filter((r) => r.is_active && r.applies_to === scopeFilter);

  return (
    <main className="mx-auto max-w-3xl">
      <span className="mb-2 block text-xs font-semibold uppercase tracking-widest text-amber-dark">
        {t("admin.requirements.eyebrow")}
      </span>
      <h1 className="font-display text-3xl font-bold text-navy">{t("admin.requirements.heading")}</h1>
      <p className="mb-6 mt-2 text-sm leading-relaxed text-steel">{t("admin.requirements.description")}</p>

      <div role="tablist" className="mb-6 inline-flex rounded-full border border-border bg-white p-1">
        <button
          type="button"
          role="tab"
          aria-selected={scopeFilter === "contractor"}
          onClick={() => setScopeFilter("contractor")}
          className={`rounded-full px-4 py-1.5 text-sm font-semibold transition-colors ${
            scopeFilter === "contractor" ? "bg-navy text-white" : "text-steel hover:text-navy"
          }`}
        >
          {t("admin.requirements.forContractors")}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={scopeFilter === "owner"}
          onClick={() => setScopeFilter("owner")}
          className={`rounded-full px-4 py-1.5 text-sm font-semibold transition-colors ${
            scopeFilter === "owner" ? "bg-navy text-white" : "text-steel hover:text-navy"
          }`}
        >
          {t("admin.requirements.forOwners")}
        </button>
      </div>

      <ErrorBanner message={error} />
      {requirementsError && <QueryError onRetry={() => refetchRequirements()} />}

      {!active.length && <p className="mb-4 text-sm text-steel">{t("admin.requirements.emptyForScope")}</p>}

      <ul className="space-y-3">
        {active.map((req) => (
          <li key={req.id} className="flex items-center gap-4 rounded border border-border bg-white px-5 py-4 shadow-sm">
            <button
              type="button"
              onClick={() => toggleRequiredMutation.mutate({ id: req.id, value: !req.is_required })}
              aria-pressed={req.is_required}
              aria-label={`${t("admin.requirements.toggleRequiredFor")} ${req.name}`}
              className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${req.is_required ? "bg-green" : "bg-border"}`}
            >
              <span
                className={`absolute top-1 h-4 w-4 rounded-full bg-white shadow transition-all ${
                  req.is_required ? "left-6" : "left-1"
                }`}
              />
            </button>

            <div className="min-w-0 flex-1">
              <div className="font-semibold text-ink">{req.name}</div>
              {req.description && <div className="mt-0.5 text-sm text-steel">{req.description}</div>}
            </div>

            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                req.is_required ? "bg-green-tint text-green" : "bg-paper text-steel"
              }`}
            >
              {req.is_required ? t("admin.requirements.required") : t("admin.requirements.optional")}
            </span>

            <button
              type="button"
              onClick={() => removeMutation.mutate(req.id)}
              title={t("admin.requirements.removeTitle")}
              className="flex h-8 w-8 items-center justify-center rounded text-steel hover:bg-red-tint hover:text-red"
            >
              ✕
            </button>
          </li>
        ))}
      </ul>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          addMutation.mutate();
        }}
        className="mt-6 grid grid-cols-1 items-center gap-3 rounded border border-dashed border-navy/40 bg-white p-5 sm:grid-cols-[1fr_1.4fr_auto_auto]"
      >
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          placeholder={t("admin.requirements.namePlaceholder")}
          className={INPUT}
        />
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t("admin.requirements.descriptionPlaceholder")}
          className={INPUT}
        />
        <label className="flex items-center gap-2 whitespace-nowrap text-sm text-ink">
          <input
            type="checkbox"
            checked={isRequired}
            onChange={(e) => setIsRequired(e.target.checked)}
            className="h-4 w-4 accent-navy"
          />
          {t("admin.requirements.required")}
        </label>
        <button
          type="submit"
          className="whitespace-nowrap rounded bg-navy px-5 py-2.5 text-sm font-semibold text-white hover:bg-navy-deep"
        >
          {scopeFilter === "owner" ? t("admin.requirements.addForOwners") : t("admin.requirements.addForContractors")}
        </button>
      </form>
    </main>
  );
}
