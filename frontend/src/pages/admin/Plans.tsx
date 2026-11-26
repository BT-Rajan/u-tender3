import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { AdminPlan } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { QueryError } from "@/components/QueryError";
import { errorText } from "@/lib/errors";

const INPUT =
  "w-full rounded border border-border bg-white px-3 py-2 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20";

interface PlanForm {
  name: string;
  description: string;
  activation_fee: string;
  monthly_fee: string;
  currency: string;
  is_active: boolean;
}

const EMPTY_FORM: PlanForm = {
  name: "",
  description: "",
  activation_fee: "0",
  monthly_fee: "",
  currency: "KWD",
  is_active: true,
};

function toBody(form: PlanForm) {
  return { ...form, description: form.description.trim() || null, currency: form.currency.trim().toUpperCase() };
}

function PlanFields({ form, setForm }: { form: PlanForm; setForm: (next: PlanForm) => void }) {
  const set = <K extends keyof PlanForm>(key: K, value: PlanForm[K]) => setForm({ ...form, [key]: value });
  return (
    <>
      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-steel">Name</label>
        <input required minLength={2} value={form.name} onChange={(e) => set("name", e.target.value)} className={INPUT} />
      </div>
      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-steel">Currency</label>
        <input required minLength={3} maxLength={3} value={form.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} className={INPUT} />
      </div>
      <div className="sm:col-span-2">
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-steel">Description (optional)</label>
        <input value={form.description} onChange={(e) => set("description", e.target.value)} className={INPUT} />
      </div>
      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-steel">Activation fee (once)</label>
        <input type="number" min="0" step="0.001" required value={form.activation_fee} onChange={(e) => set("activation_fee", e.target.value)} className={INPUT} />
      </div>
      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-steel">Monthly fee</label>
        <input type="number" min="0.001" step="0.001" required value={form.monthly_fee} onChange={(e) => set("monthly_fee", e.target.value)} className={INPUT} />
      </div>
      <label className="flex items-center gap-2 text-sm sm:col-span-2">
        <input type="checkbox" checked={form.is_active} onChange={(e) => set("is_active", e.target.checked)} />
        Show this plan to contractors
      </label>
    </>
  );
}

export function AdminPlansPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<PlanForm>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<PlanForm>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const { data: plans, isError, refetch } = useQuery({
    queryKey: ["admin-plans"],
    queryFn: () => apiFetch<AdminPlan[]>("/admin/plans"),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin-plans"] });

  const create = useMutation({
    mutationFn: () => apiFetch<AdminPlan>("/admin/plans", { method: "POST", body: toBody(form) }),
    onSuccess: () => {
      setError(null);
      setForm(EMPTY_FORM);
      refresh();
    },
    onError: (err) => setError(errorText(err, "Could not save the plan.")),
  });

  const update = useMutation({
    mutationFn: (planId: string) => apiFetch<AdminPlan>(`/admin/plans/${planId}`, { method: "PATCH", body: toBody(editForm) }),
    onSuccess: () => {
      setError(null);
      setEditingId(null);
      refresh();
    },
    onError: (err) => setError(errorText(err, "Could not update the plan.")),
  });

  const remove = useMutation({
    mutationFn: (planId: string) => apiFetch(`/admin/plans/${planId}`, { method: "DELETE" }),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (err) => setError(errorText(err, "Could not delete the plan.")),
  });

  function startEdit(plan: AdminPlan) {
    setError(null);
    setEditingId(plan.id);
    setEditForm({
      name: plan.name,
      description: plan.description ?? "",
      activation_fee: plan.activation_fee,
      monthly_fee: plan.monthly_fee,
      currency: plan.currency,
      is_active: plan.is_active,
    });
  }

  function confirmDelete(plan: AdminPlan) {
    if (window.confirm(`Delete the plan "${plan.name}"? This cannot be undone. A plan with payment history cannot be deleted.`)) {
      remove.mutate(plan.id);
    }
  }

  return (
    <main className="mx-auto max-w-5xl">
      <div className="mb-6">
        <span className="mb-1 block text-xs font-semibold uppercase tracking-widest text-amber-dark">Admin · Plans</span>
        <h1 className="mb-1 font-display text-3xl font-bold text-navy">Subscription plans</h1>
        <p className="text-[13.5px] text-steel">
          The activation fee is paid once, with the first month. The monthly fee is paid each month after that. Hide a plan to stop offering it without losing its history.
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          create.mutate();
        }}
        className="mb-8 grid gap-4 rounded-lg border border-border bg-white p-5 shadow-sm sm:grid-cols-2"
      >
        <PlanFields form={form} setForm={setForm} />
        <div className="sm:col-span-2">
          <button type="submit" disabled={create.isPending} className="rounded bg-amber px-5 py-2.5 text-sm font-semibold text-white hover:bg-amber-dark disabled:opacity-60">
            {create.isPending ? "Saving..." : "Add plan"}
          </button>
        </div>
      </form>

      <ErrorBanner message={error} />

      {isError ? (
        <QueryError onRetry={() => refetch()} />
      ) : !plans?.length ? (
        <div className="rounded-lg border border-dashed border-border bg-white p-10 text-center text-sm text-steel">No plans yet.</div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-white shadow-sm">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="border-b border-border px-2.5 py-2 text-left text-xs font-semibold uppercase tracking-wide text-steel">Plan</th>
                <th className="border-b border-border px-2.5 py-2 text-left text-xs font-semibold uppercase tracking-wide text-steel">Activation</th>
                <th className="border-b border-border px-2.5 py-2 text-left text-xs font-semibold uppercase tracking-wide text-steel">Monthly</th>
                <th className="border-b border-border px-2.5 py-2 text-left text-xs font-semibold uppercase tracking-wide text-steel">Shown</th>
                <th className="border-b border-border px-2.5 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {plans.map((plan) =>
                editingId === plan.id ? (
                  <tr key={plan.id} className="border-b border-border bg-paper">
                    <td colSpan={5} className="px-2.5 py-4">
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          setError(null);
                          update.mutate(plan.id);
                        }}
                        className="grid gap-4 sm:grid-cols-2"
                      >
                        <PlanFields form={editForm} setForm={setEditForm} />
                        <div className="flex gap-2 sm:col-span-2">
                          <button type="submit" disabled={update.isPending} className="rounded bg-navy px-4 py-2 text-xs font-semibold text-white disabled:opacity-60">
                            Save plan
                          </button>
                          <button type="button" onClick={() => setEditingId(null)} className="rounded border border-navy px-4 py-2 text-xs font-semibold text-navy">
                            Cancel
                          </button>
                        </div>
                      </form>
                    </td>
                  </tr>
                ) : (
                  <tr key={plan.id} className="border-b border-border">
                    <td className="px-2.5 py-3">
                      <div className="font-display text-[13.5px] font-semibold">{plan.name}</div>
                      {plan.description && <div className="text-[11.5px] text-steel-light">{plan.description}</div>}
                    </td>
                    <td className="px-2.5 py-3 font-mono text-[12.5px]">
                      {plan.activation_fee} {plan.currency}
                    </td>
                    <td className="px-2.5 py-3 font-mono text-[12.5px]">
                      {plan.monthly_fee} {plan.currency}
                    </td>
                    <td className="px-2.5 py-3">
                      <span className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase ${plan.is_active ? "bg-green-tint text-green" : "bg-blue-tint text-steel"}`}>
                        {plan.is_active ? "Yes" : "Hidden"}
                      </span>
                    </td>
                    <td className="space-x-2 px-2.5 py-3 text-right">
                      <button type="button" onClick={() => startEdit(plan)} className="rounded-md border border-navy px-3 py-1.5 text-xs font-semibold text-navy hover:bg-navy hover:text-white">
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => confirmDelete(plan)}
                        disabled={remove.isPending}
                        className="rounded-md bg-red-tint px-3 py-1.5 text-xs font-semibold text-red disabled:opacity-60"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                )
              )}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
