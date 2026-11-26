import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { BusinessDetails } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { PageLoading } from "@/components/PageLoading";
import { useI18n } from "@/i18n/I18nContext";
import { errorText } from "@/lib/errors";

// Must match TRADE_OPTIONS in backend/app/services/registration.py.
export const TRADE_OPTIONS = [
  "General contracting",
  "Electrical",
  "Plumbing",
  "HVAC",
  "Civil works",
  "Finishing",
  "Fire safety",
  "Landscaping",
  "Other",
] as const;

const INPUT =
  "w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20";

export function ContractorOnboardingPage() {
  const { data, isError } = useQuery({
    queryKey: ["contractor-onboarding"],
    queryFn: () => apiFetch<BusinessDetails>("/contractor/onboarding"),
  });
  if (isError) return <ErrorBanner message="Could not load your details. Refresh the page." />;
  if (!data) return <PageLoading />;
  return <Wizard initial={data} />;
}

// Two steps: business details, then the trades offered. Saved in one request at the end.
function Wizard({ initial }: { initial: BusinessDetails }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [step, setStep] = useState<1 | 2>(1);
  const [name, setName] = useState(initial.business_name ?? "");
  const [address, setAddress] = useState(initial.business_address ?? "");
  const [website, setWebsite] = useState(initial.website ?? "");
  const [email, setEmail] = useState(initial.business_email ?? "");
  const [registrationId, setRegistrationId] = useState(initial.business_registration_id ?? "");
  const [trades, setTrades] = useState<string[]>(initial.trades ?? []);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () =>
      apiFetch<BusinessDetails>("/contractor/onboarding", {
        method: "PUT",
        body: {
          business_name: name.trim(),
          business_address: address.trim(),
          website: website.trim() || null,
          business_email: email.trim(),
          business_registration_id: registrationId.trim(),
          trades,
        },
      }),
    onSuccess: () => navigate("/contractor/subscribe"),
    onError: (err) => setError(errorText(err, t("onboarding.wizardError"))),
  });

  function toggleTrade(trade: string) {
    setTrades((current) => (current.includes(trade) ? current.filter((x) => x !== trade) : [...current, trade]));
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (step === 1) {
      setStep(2);
      return;
    }
    if (trades.length === 0) {
      setError(t("onboarding.tradesRequired"));
      return;
    }
    save.mutate();
  }

  return (
    <main className="mx-auto max-w-2xl px-5 py-8">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-widest text-amber-dark">{t("onboarding.wizardEyebrow")}</span>
      <h1 className="mb-1 font-display text-3xl font-bold text-navy">{t("onboarding.wizardHeading")}</h1>
      <p className="mb-6 text-[13.5px] text-steel">{t("onboarding.wizardIntro")}</p>

      <ol className="mb-6 flex gap-3 text-xs font-semibold uppercase tracking-wide">
        <li className={step === 1 ? "text-navy" : "text-steel"}>1. {t("onboarding.step1")}</li>
        <li className={step === 2 ? "text-navy" : "text-steel"}>2. {t("onboarding.step2")}</li>
      </ol>

      <ErrorBanner message={error} />

      <form onSubmit={handleSubmit} className="mt-4 grid gap-5">
        {step === 1 && (
          <>
            <div>
              <label htmlFor="ob-name" className="mb-1.5 block text-sm font-medium text-ink">{t("onboarding.businessName")}</label>
              <input id="ob-name" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} className={INPUT} />
            </div>
            <div>
              <label htmlFor="ob-address" className="mb-1.5 block text-sm font-medium text-ink">{t("onboarding.address")}</label>
              <input id="ob-address" required minLength={5} value={address} onChange={(e) => setAddress(e.target.value)} className={INPUT} />
            </div>
            <div>
              <label htmlFor="ob-website" className="mb-1.5 block text-sm font-medium text-ink">{t("onboarding.website")}</label>
              <input id="ob-website" value={website} onChange={(e) => setWebsite(e.target.value)} className={INPUT} />
              <p className="mt-1 text-xs text-steel-light">{t("onboarding.websiteHint")}</p>
            </div>
            <div>
              <label htmlFor="ob-email" className="mb-1.5 block text-sm font-medium text-ink">{t("onboarding.businessEmail")}</label>
              <input id="ob-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={INPUT} />
            </div>
            <div>
              <label htmlFor="ob-reg" className="mb-1.5 block text-sm font-medium text-ink">{t("onboarding.registrationId")}</label>
              <input id="ob-reg" required minLength={2} value={registrationId} onChange={(e) => setRegistrationId(e.target.value)} className={INPUT} />
            </div>
            <button type="submit" className="w-fit rounded bg-amber px-5 py-3 text-sm font-semibold text-white hover:bg-amber-dark">
              {t("onboarding.next")}
            </button>
          </>
        )}

        {step === 2 && (
          <>
            <div>
              <p className="mb-1 text-sm font-medium text-ink">{t("onboarding.tradesHeading")}</p>
              <p className="mb-3 text-xs text-steel-light">{t("onboarding.tradesHint")}</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {TRADE_OPTIONS.map((trade) => (
                  <label key={trade} className="flex items-center gap-2.5 rounded border border-border bg-white px-3.5 py-2.5 text-sm">
                    <input type="checkbox" checked={trades.includes(trade)} onChange={() => toggleTrade(trade)} />
                    {trade}
                  </label>
                ))}
              </div>
            </div>
            <div className="flex gap-3">
              <button type="button" onClick={() => setStep(1)} className="rounded border border-navy px-5 py-3 text-sm font-semibold text-navy hover:bg-navy hover:text-white">
                {t("onboarding.back")}
              </button>
              <button
                type="submit"
                disabled={save.isPending}
                className="rounded bg-amber px-5 py-3 text-sm font-semibold text-white hover:bg-amber-dark disabled:opacity-60"
              >
                {save.isPending ? t("onboarding.saving") : t("onboarding.save")}
              </button>
            </div>
          </>
        )}
      </form>
    </main>
  );
}
