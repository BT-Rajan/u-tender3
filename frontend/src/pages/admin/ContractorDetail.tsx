import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { AuditLogEntry, ContractorProfile, PaymentOverrideRecord } from "@/api/types";
import { formatDate, formatDateTime, stars } from "@/lib/format";
import { errorText } from "@/lib/errors";
import { DeleteContractorForm } from "@/components/DeleteContractorForm";
import { ErrorBanner } from "@/components/ErrorBanner";
import { PageLoading } from "@/components/PageLoading";
import { useI18n } from "@/i18n/I18nContext";

const STATUS_OPTIONS = ["incomplete", "pending_review", "changes_requested", "approved"] as const;

const MARKETPLACE_STATUS_LABEL: Record<string, string> = {
  documents_incomplete: "Documents incomplete",
  submitted_for_review: "Submitted for review",
  changes_requested: "Changes requested",
  payment_required: "Payment required",
  verified_active: "Verified & active",
  suspended: "Suspended",
};

const MARKETPLACE_STATUS_BADGE: Record<string, string> = {
  documents_incomplete: "bg-blue-tint text-steel",
  submitted_for_review: "bg-amber/15 text-amber-dark",
  changes_requested: "bg-red-tint text-red",
  payment_required: "bg-amber/15 text-amber-dark",
  verified_active: "bg-green-tint text-green",
  suspended: "bg-red-tint text-red",
};

function MarketplaceAccessPanel({ contractorId, contractor }: { contractorId: string; contractor: ContractorProfile }) {
  const { language } = useI18n();
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: overrides } = useQuery({
    queryKey: ["admin-payment-overrides", contractorId],
    queryFn: () => apiFetch<PaymentOverrideRecord[]>(`/admin/contractors/${contractorId}/payment-overrides`),
  });

  const invalidate = () => {
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["admin-contractor", contractorId] });
    queryClient.invalidateQueries({ queryKey: ["admin-payment-overrides", contractorId] });
    queryClient.invalidateQueries({ queryKey: ["admin-audit-log", contractorId] });
  };

  const grantMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/contractors/${contractorId}/payment-override`, { method: "POST", body: { reason } }),
    onSuccess: () => {
      setReason("");
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Could not grant override."),
  });

  const revokeMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/admin/contractors/${contractorId}/payment-override/revoke`, { method: "POST", body: { reason: reason || null } }),
    onSuccess: () => {
      setReason("");
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Could not revoke override."),
  });

  const label = MARKETPLACE_STATUS_LABEL[contractor.marketplace_status] ?? contractor.marketplace_status;
  const badge = MARKETPLACE_STATUS_BADGE[contractor.marketplace_status] ?? "bg-blue-tint text-steel";

  return (
    <div className="bg-white border border-border rounded-lg shadow-sm px-5 py-4.5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-navy mb-3">Marketplace access</h3>
      <div className="flex items-center gap-2 mb-3">
        <span className={`font-mono text-[10px] uppercase px-2.5 py-1 rounded-full ${badge}`}>{label}</span>
        {contractor.payment_override_active && (
          <span className="font-mono text-[10px] uppercase px-2.5 py-1 rounded-full bg-blue-tint text-blue">Admin override active</span>
        )}
      </div>
      <p className="text-[11.5px] text-steel-light mb-3">
        Paid until: {contractor.paid_until ? formatDate(contractor.paid_until, language) : "not paid"}
        {" · "}
        Trial until: {contractor.trial_until ? formatDate(contractor.trial_until, language) : "none"}
      </p>

      <ErrorBanner message={error} />

      <label className="block text-xs font-semibold uppercase tracking-wide text-steel mb-1">
        {contractor.payment_override_active ? "Revoke reason (optional)" : "Override reason (required)"}
      </label>
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        rows={2}
        placeholder="Why is this override needed? This is recorded permanently."
        className="w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20 mb-2 resize-y"
      />
      {contractor.payment_override_active ? (
        <button
          type="button"
          onClick={() => revokeMutation.mutate()}
          disabled={revokeMutation.isPending}
          className="bg-red-tint text-red text-xs font-semibold rounded px-4 py-2 disabled:opacity-60"
        >
          Revoke override
        </button>
      ) : (
        <button
          type="button"
          onClick={() => grantMutation.mutate()}
          disabled={grantMutation.isPending || !reason.trim()}
          className="border border-navy text-navy hover:bg-navy hover:text-white text-xs font-semibold rounded-md px-4 py-2 disabled:opacity-40"
        >
          Grant payment override
        </button>
      )}

      {!!overrides?.length && (
        <div className="mt-4 border-t border-border pt-3">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-steel mb-2">Override history</h4>
          <ul className="space-y-2">
            {overrides.map((o) => (
              <li key={o.id} className="text-[11.5px] text-steel">
                <span className="font-mono text-[10px] text-steel-light">{formatDateTime(o.created_at, language)}</span>
                {" — "}
                {o.reason}
                {o.revoked_at && <span className="text-red"> (revoked {formatDateTime(o.revoked_at, language)})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// The date an ISO UTC timestamp falls on in Kuwait, as YYYY-MM-DD for a date input. Empty when there is none.
function kuwaitDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(`${iso}Z`).toLocaleDateString("en-CA", { timeZone: "Asia/Kuwait" });
}

// Paid-until and trial-until, set by hand. Only the dates that change are sent, each with the reason.
function BillingDatesPanel({ contractorId, contractor }: { contractorId: string; contractor: ContractorProfile }) {
  const queryClient = useQueryClient();
  const initialPaid = kuwaitDate(contractor.paid_until);
  const initialTrial = kuwaitDate(contractor.trial_until);
  const [paid, setPaid] = useState(initialPaid);
  const [trial, setTrial] = useState(initialTrial);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPaid(initialPaid);
    setTrial(initialTrial);
  }, [initialPaid, initialTrial]);

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, string | null> = { reason: reason.trim() };
      if (paid !== initialPaid) body.paid_until = paid || null;
      if (trial !== initialTrial) body.trial_until = trial || null;
      return apiFetch(`/admin/contractors/${contractorId}/billing`, { method: "PATCH", body });
    },
    onSuccess: () => {
      setReason("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-contractor", contractorId] });
      queryClient.invalidateQueries({ queryKey: ["admin-audit-log", contractorId] });
    },
    onError: (err) => setError(errorText(err, "Could not save the billing dates.")),
  });

  const unchanged = paid === initialPaid && trial === initialTrial;
  const INPUT_CLASS = "w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20";

  return (
    <div className="bg-white border border-border rounded-lg shadow-sm px-5 py-4.5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-navy mb-3">Billing dates</h3>
      <p className="text-[11.5px] text-steel-light mb-3">
        A trial lets this contractor send offers without a paid subscription, until the trial date. Approval is still required. Dates end at 23:59 Kuwait time. Clear a date to remove it.
      </p>
      <ErrorBanner message={error} />
      <div className="grid gap-3">
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-steel mb-1">Paid until</label>
          <input type="date" value={paid} onChange={(e) => setPaid(e.target.value)} className={INPUT_CLASS} />
        </div>
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-steel mb-1">Trial until</label>
          <input type="date" value={trial} onChange={(e) => setTrial(e.target.value)} className={INPUT_CLASS} />
        </div>
        <label className="block text-xs font-semibold uppercase tracking-wide text-steel">Reason (required)</label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          placeholder="Why is this changed? This is recorded permanently."
          className={`${INPUT_CLASS} resize-y`}
        />
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={save.isPending || unchanged || reason.trim().length < 3}
          className="bg-navy hover:bg-navy-deep text-white font-semibold text-sm rounded px-4 py-2 w-fit disabled:opacity-40"
        >
          Save billing dates
        </button>
      </div>
    </div>
  );
}

function ActivityLogPanel({ contractorId }: { contractorId: string }) {
  const { language } = useI18n();
  const { data: entries } = useQuery({
    queryKey: ["admin-audit-log", contractorId],
    queryFn: () => apiFetch<AuditLogEntry[]>(`/admin/contractors/${contractorId}/audit-log`),
  });

  if (!entries?.length) return null;

  return (
    <div className="bg-white border border-border rounded-lg shadow-sm px-5 py-4.5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-navy mb-3">Activity log</h3>
      <ul className="space-y-2 max-h-64 overflow-y-auto">
        {entries.map((e) => (
          <li key={e.id} className="text-[11.5px] text-steel border-b border-border pb-2 last:border-0">
            <div className="font-mono text-[10px] text-steel-light">{formatDateTime(e.created_at, language)}</div>
            <div>
              <span className="font-semibold text-navy">{e.action}</span>
              {e.previous_value !== null && e.new_value !== null && (
                <span className="text-steel-light">
                  {" "}
                  ({e.previous_value} → {e.new_value})
                </span>
              )}
            </div>
            {e.reason && <div className="text-steel-light italic">"{e.reason}"</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AdminContractorDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: detail } = useQuery({
    queryKey: ["admin-contractor", id],
    queryFn: () => apiFetch<{ contractor: ContractorProfile }>(`/admin/contractors/${id}`),
    enabled: !!id,
  });
  const contractor = detail?.contractor;

  const [companyName, setCompanyName] = useState("");
  const [licenseNumber, setLicenseNumber] = useState("");
  const [primaryTrade, setPrimaryTrade] = useState("");
  const [serviceArea, setServiceArea] = useState("");
  const [statusValue, setStatusValue] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!contractor) return;
    setCompanyName(contractor.company_name);
    setLicenseNumber(contractor.license_number ?? "");
    setPrimaryTrade(contractor.primary_trade ?? "");
    setServiceArea(contractor.service_area ?? "");
    setStatusValue(contractor.verification_status);
  }, [contractor?.user_id]);

  const invalidate = () => {
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["admin-contractor", id] });
    queryClient.invalidateQueries({ queryKey: ["admin-contractors"] });
  };
  const onMutationError = (err: unknown, fallback: string) =>
    setError(err instanceof ApiError ? err.detail : fallback);

  const updateMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/admin/contractors/${id}`, {
        method: "PATCH",
        body: { company_name: companyName, license_number: licenseNumber || null, primary_trade: primaryTrade || null, service_area: serviceArea || null },
      }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, "Could not save changes."),
  });

  const statusMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/contractors/${id}/verification-status`, { method: "POST", body: { status: statusValue } }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, "Could not update verification status."),
  });

  const suspendMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/contractors/${id}/suspend`, { method: "POST", body: { suspended: !contractor?.is_suspended } }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, "Could not update account access."),
  });

  if (!contractor) return <PageLoading />;

  return (
    <main className="max-w-3xl mx-auto px-5 py-8">
      <span className="text-xs font-semibold uppercase tracking-widest text-amber-dark block mb-1">Admin · Contractors</span>
      <div className="flex items-start justify-between flex-wrap gap-3 mb-6">
        <div>
          <h1 className="font-display text-3xl font-bold text-navy mb-1">{contractor.company_name}</h1>
          <Link to={`/admin/users/${id}/history`} className="text-sm font-semibold text-navy hover:underline">
            {t("history.link")}
          </Link>
          <p className="text-[13.5px] text-steel">
            <span className="text-amber">{stars(Number(contractor.avg_rating))}</span>{" "}
            <span className="font-mono text-steel">({contractor.review_count} reviews)</span>
          </p>
        </div>
        {contractor.is_suspended && <span className="font-mono text-[10px] uppercase px-2.5 py-1 rounded-full bg-red-tint text-red">Suspended</span>}
      </div>

      <ErrorBanner message={error} />

      <div className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr] gap-6 items-start">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            updateMutation.mutate();
          }}
          className="grid gap-4 bg-white border border-border rounded-lg shadow-sm px-5 py-4.5"
        >
          <h3 className="text-xs font-semibold uppercase tracking-wide text-navy -mb-1">Company details</h3>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-steel mb-1">Company name</label>
            <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} required className="w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20" />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-steel mb-1">License number</label>
            <input value={licenseNumber} onChange={(e) => setLicenseNumber(e.target.value)} className="w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20" />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-steel mb-1">Primary trade</label>
            <input value={primaryTrade} onChange={(e) => setPrimaryTrade(e.target.value)} className="w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20" />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-steel mb-1">Service area</label>
            <input value={serviceArea} onChange={(e) => setServiceArea(e.target.value)} className="w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20" />
          </div>
          <button type="submit" className="bg-navy hover:bg-navy-deep text-white font-semibold text-sm rounded px-4 py-2 w-fit">
            Save changes
          </button>
        </form>

        <div className="grid gap-4">
          <div className="bg-white border border-border rounded-lg shadow-sm px-5 py-4.5">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-navy mb-3">Verification status</h3>
            <div className="flex items-center gap-2">
              <select value={statusValue} onChange={(e) => setStatusValue(e.target.value)} className="rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20 flex-1">
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s.replace("_", " ")}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => statusMutation.mutate()}
                className="border border-navy text-navy hover:bg-navy hover:text-white text-xs font-semibold rounded-md px-3 py-2"
              >
                Update
              </button>
            </div>
            <p className="text-[11px] text-steel-light mt-2">Admin override — bypasses the per-document review flow. Use with care.</p>
          </div>

          <MarketplaceAccessPanel contractorId={contractor.user_id} contractor={contractor} />

          <BillingDatesPanel contractorId={contractor.user_id} contractor={contractor} />

          <div className="bg-white border border-border rounded-lg shadow-sm px-5 py-4.5">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-navy mb-3">Account access</h3>
            <button
              type="button"
              onClick={() => suspendMutation.mutate()}
              className={`text-xs font-semibold rounded px-4 py-2 w-full ${contractor.is_suspended ? "bg-green-tint text-green" : "bg-red-tint text-red"}`}
            >
              {contractor.is_suspended ? "Reactivate account" : "Suspend account"}
            </button>
            <p className="text-[11px] text-steel-light mt-2">
              {contractor.is_suspended
                ? "This contractor can't view projects, drawings, or submit offers until reactivated."
                : "Immediately blocks the contractor from the feed and offers, without deleting anything."}
            </p>
          </div>

          <ActivityLogPanel contractorId={contractor.user_id} />

          <div className="bg-white border border-red/30 rounded px-5 py-4.5">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-red mb-3">Danger zone</h3>
            <DeleteContractorForm
              contractorId={contractor.user_id}
              companyName={contractor.company_name}
              onDeleted={() => navigate("/admin/contractors")}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
