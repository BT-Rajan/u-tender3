import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { ContractorStatus, PaymentInvoiceItem, SubscriptionPlanItem } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { PageLoading } from "@/components/PageLoading";
import { useI18n } from "@/i18n/I18nContext";
import { formatDate } from "@/lib/format";
import { errorText } from "@/lib/errors";

function invoiceStatusLabel(status: PaymentInvoiceItem["status"], t: (key: string) => string): string {
  switch (status) {
    case "pending":
      return t("onboarding.statusPending");
    case "paid":
      return t("onboarding.statusPaid");
    case "canceled":
      return t("onboarding.statusCanceled");
    default:
      return t("onboarding.statusExpired");
  }
}

export function ContractorSubscribePage() {
  const { t, language } = useI18n();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const failed = params.has("failed");
  const returned = params.has("paid") || failed;
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const checkedRef = useRef(false);

  const { data: status } = useQuery({
    queryKey: ["contractor-status"],
    queryFn: () => apiFetch<ContractorStatus>("/contractor/status"),
  });
  const { data: plans, isError: plansFailed } = useQuery({
    queryKey: ["billing-plans"],
    queryFn: () => apiFetch<SubscriptionPlanItem[]>("/billing/plans"),
  });
  const { data: invoices } = useQuery({
    queryKey: ["billing-invoices"],
    queryFn: () => apiFetch<PaymentInvoiceItem[]>("/billing/invoices"),
  });

  // Back from MyFatoorah: ask the server to check each invoice that is still pending. Once per visit.
  useEffect(() => {
    if (!returned || !invoices || checkedRef.current) return;
    checkedRef.current = true;
    const pending = invoices.filter((invoice) => invoice.status === "pending");
    if (pending.length === 0) return;
    setChecking(true);
    Promise.all(pending.map((invoice) => apiFetch(`/billing/invoices/${invoice.id}/refresh`, { method: "POST" }).catch(() => null)))
      .finally(() => {
        setChecking(false);
        queryClient.invalidateQueries({ queryKey: ["billing-invoices"] });
        queryClient.invalidateQueries({ queryKey: ["contractor-status"] });
        queryClient.invalidateQueries({ queryKey: ["contractor-profile"] });
      });
  }, [returned, invoices, queryClient]);

  const pay = useMutation({
    mutationFn: (planId: string) =>
      apiFetch<PaymentInvoiceItem>("/billing/invoices", { method: "POST", body: { plan_id: planId } }),
    onSuccess: (invoice) => {
      if (invoice.payment_url) {
        window.location.href = invoice.payment_url;
        return;
      }
      setError(t("onboarding.paymentError"));
    },
    onError: (err) => setError(errorText(err, t("onboarding.paymentError"))),
  });

  function continueToPayment(invoice: PaymentInvoiceItem) {
    if (invoice.payment_url) window.location.href = invoice.payment_url;
  }

  if (!plans && !plansFailed) return <PageLoading />;

  const activationPaid = invoices?.some((invoice) => invoice.kind === "activation" && invoice.status === "paid") ?? false;

  return (
    <main className="mx-auto max-w-3xl px-5 py-8">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-widest text-amber-dark">{t("onboarding.subEyebrow")}</span>
      <h1 className="mb-1 font-display text-3xl font-bold text-navy">{t("onboarding.subHeading")}</h1>
      <p className="mb-6 text-[13.5px] text-steel">{t("onboarding.subIntro")}</p>

      {status?.trial_active && status.trial_until && (
        <p role="status" className="mb-4 rounded border border-blue bg-blue-tint px-3.5 py-2.5 text-sm text-blue">
          {t("onboarding.trialNote")} {formatDate(status.trial_until, language)}
        </p>
      )}

      {status?.paid_until && (
        <p className="mb-4 font-mono text-[11px] text-steel">
          {t("onboarding.paidUntil")} {formatDate(status.paid_until, language)}
        </p>
      )}

      {returned && (
        <p
          role="status"
          className={`mb-4 rounded border px-3.5 py-2.5 text-sm ${failed ? "border-red bg-red-tint text-red" : "border-blue bg-blue-tint text-blue"}`}
        >
          {failed ? t("onboarding.failedNotice") : t("onboarding.paidNotice")}
        </p>
      )}
      {checking && <p className="mb-4 text-sm text-steel">{t("onboarding.checkingPayment")}</p>}
      <ErrorBanner message={error} />

      {plansFailed || (plans && plans.length === 0) ? (
        <p className="rounded border border-dashed border-border bg-white p-6 text-sm text-steel">{t("onboarding.noPlans")}</p>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2">
          {plans?.map((plan) => {
            const firstTotal = (Number(plan.activation_fee) + Number(plan.monthly_fee)).toFixed(3);
            const opening = pay.isPending && pay.variables === plan.id;
            return (
              <div key={plan.id} className="flex flex-col rounded border border-border border-t-4 border-t-amber bg-white px-6 py-6">
                <div className="font-display text-xl font-bold text-navy">{plan.name}</div>
                {plan.description && <p className="mt-1 text-sm text-steel">{plan.description}</p>}
                <dl className="mt-4 space-y-2 text-sm">
                  {!activationPaid && (
                    <div className="flex justify-between gap-4">
                      <dt className="text-steel">{t("onboarding.activationFee")}</dt>
                      <dd>
                        {plan.activation_fee} {plan.currency}
                      </dd>
                    </div>
                  )}
                  <div className="flex justify-between gap-4">
                    <dt className="text-steel">{t("onboarding.monthlyFee")}</dt>
                    <dd>
                      {plan.monthly_fee} {plan.currency}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-4 border-t border-border pt-2 font-semibold">
                    <dt>{activationPaid ? t("onboarding.monthlyPayment") : t("onboarding.firstPayment")}</dt>
                    <dd>
                      {activationPaid ? Number(plan.monthly_fee).toFixed(3) : firstTotal} {plan.currency}
                    </dd>
                  </div>
                </dl>
                <button
                  type="button"
                  onClick={() => pay.mutate(plan.id)}
                  disabled={pay.isPending}
                  className="mt-6 rounded bg-amber px-5 py-2.5 text-sm font-semibold text-white hover:bg-amber-dark disabled:opacity-60"
                >
                  {opening ? t("onboarding.opening") : t("onboarding.payWithMyFatoorah")}
                </button>
              </div>
            );
          })}
        </div>
      )}

      <h2 className="mb-3 mt-10 font-display text-lg font-bold text-navy">{t("onboarding.invoices")}</h2>
      {!invoices?.length ? (
        <p className="text-sm text-steel">{t("onboarding.noInvoices")}</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-white shadow-sm">
          <table className="w-full border-collapse text-sm">
            <tbody>
              {invoices.map((invoice) => (
                <tr key={invoice.id} className="border-b border-border">
                  <td className="px-3 py-3">{formatDate(invoice.created_at, language)}</td>
                  <td className="px-3 py-3">{invoice.kind === "activation" ? t("onboarding.activationFee") : t("onboarding.monthlyFee")}</td>
                  <td className="px-3 py-3 font-mono">
                    {invoice.amount} {invoice.currency}
                  </td>
                  <td className="px-3 py-3">
                    <span className="font-mono text-[10px] uppercase">{invoiceStatusLabel(invoice.status, t)}</span>
                  </td>
                  <td className="px-3 py-3 text-right">
                    {invoice.status === "pending" && invoice.payment_url && (
                      <button
                        type="button"
                        onClick={() => continueToPayment(invoice)}
                        className="rounded border border-navy px-3 py-1.5 text-xs font-semibold text-navy hover:bg-navy hover:text-white"
                      >
                        {t("onboarding.continuePayment")}
                      </button>
                    )}
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
