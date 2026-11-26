import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { ActivationRow } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { QueryError } from "@/components/QueryError";
import { formatDateTime } from "@/lib/format";
import { errorText } from "@/lib/errors";

// Paid contractors waiting for the admin's check. Each row shows the 48-hour deadline.
export function AdminActivationsPage() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { data: rows, isError, refetch } = useQuery({
    queryKey: ["admin-activations"],
    queryFn: () => apiFetch<ActivationRow[]>("/admin/activations?status=pending"),
  });

  const activate = useMutation({
    mutationFn: (contractorId: string) => apiFetch(`/admin/contractors/${contractorId}/activate`, { method: "POST" }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-activations"] });
      queryClient.invalidateQueries({ queryKey: ["admin-contractors"] });
    },
    onError: (err) => setError(errorText(err, "Could not activate this contractor.")),
  });

  return (
    <main className="mx-auto max-w-5xl">
      <div className="mb-6">
        <span className="mb-1 block text-xs font-semibold uppercase tracking-widest text-amber-dark">Admin · Activations</span>
        <h1 className="mb-1 font-display text-3xl font-bold text-navy">Waiting for activation</h1>
        <p className="text-[13.5px] text-steel">
          Check each contractor's business details before you activate. Activation is due within 48 hours of the first payment.
        </p>
      </div>

      <ErrorBanner message={error} />

      {isError ? (
        <QueryError onRetry={() => refetch()} />
      ) : !rows?.length ? (
        <div className="rounded-lg border border-dashed border-border bg-white p-10 text-center text-sm text-steel">
          No contractors are waiting for activation.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-white shadow-sm">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="border-b border-border px-2.5 py-2 text-left text-xs font-semibold uppercase tracking-wide text-steel">Company</th>
                <th className="border-b border-border px-2.5 py-2 text-left text-xs font-semibold uppercase tracking-wide text-steel">Contact</th>
                <th className="border-b border-border px-2.5 py-2 text-left text-xs font-semibold uppercase tracking-wide text-steel">Deadline</th>
                <th className="border-b border-border px-2.5 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.contractor_id} className="border-b border-border">
                  <td className="px-2.5 py-3">
                    <div className="font-display text-[13.5px] font-semibold">{row.company_name}</div>
                    <Link to={`/admin/contractors/${row.contractor_id}`} className="text-[11.5px] text-navy underline">
                      Review details
                    </Link>
                  </td>
                  <td className="px-2.5 py-3 text-[12.5px]">
                    <div>{row.contact_name ?? "-"}</div>
                    <div className="text-steel">{row.email ?? "-"}</div>
                    <div className="font-mono text-steel">{row.phone ?? "-"}</div>
                  </td>
                  <td className="px-2.5 py-3 text-[12.5px]">
                    <div className="font-mono">{formatDateTime(row.activation_due_at, "en")}</div>
                    {row.overdue ? (
                      <span className="mt-1 inline-block rounded-full bg-red-tint px-2 py-0.5 font-mono text-[10px] uppercase text-red">Overdue</span>
                    ) : (
                      <span className="mt-1 inline-block font-mono text-[11px] text-steel">{Math.max(0, Math.round(row.hours_left))} h left</span>
                    )}
                  </td>
                  <td className="px-2.5 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => activate.mutate(row.contractor_id)}
                      disabled={activate.isPending || !row.payment_active}
                      className="rounded-md bg-amber px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-dark disabled:opacity-60"
                    >
                      Activate
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
