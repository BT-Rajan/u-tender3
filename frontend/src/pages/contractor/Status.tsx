import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { ContractorDocument, ContractorProfile, ContractorStatus } from "@/api/types";
import { PageLoading } from "@/components/PageLoading";
import { useI18n } from "@/i18n/I18nContext";
import { formatDate } from "@/lib/format";

function statusBadge(status: string) {
  switch (status) {
    case "approved":
      return "bg-green-tint text-green";
    case "rejected":
      return "bg-red-tint text-red";
    case "pending":
      return "bg-amber/15 text-amber-dark";
    default:
      return "bg-blue-tint text-steel";
  }
}

// The next step in sign-up (details, plan, waiting for activation, or active), from GET /contractor/status.
function OnboardingPanel() {
  const { t, language } = useI18n();
  const { data: s } = useQuery({
    queryKey: ["contractor-status"],
    queryFn: () => apiFetch<ContractorStatus>("/contractor/status"),
  });
  if (!s || s.is_suspended || s.next_step === "suspended") return null;

  let title: string;
  let body: string;
  let tone = "border-amber";
  let action: { label: string; href: string } | null = null;
  let extra: string | null = null;

  if (s.next_step === "active") {
    title = t("onboarding.panelActiveTitle");
    body = t("onboarding.panelActiveBody");
    tone = "border-green";
  } else if (s.next_step === "details") {
    title = t("onboarding.panelDetailsTitle");
    body = t("onboarding.panelDetailsBody");
    action = { label: t("onboarding.panelDetailsCta"), href: "/contractor/onboarding" };
  } else if (s.next_step === "subscribe") {
    title = t("onboarding.panelSubscribeTitle");
    body = t("onboarding.panelSubscribeBody");
    action = { label: t("onboarding.panelSubscribeCta"), href: "/contractor/subscribe" };
  } else {
    title = t("onboarding.panelAwaitingTitle");
    body = t("onboarding.panelAwaitingBody");
    if (s.activation_due_at) extra = `${t("onboarding.panelDueBy")} ${formatDate(s.activation_due_at, language)}`;
  }

  return (
    <div className={`mb-6 flex flex-wrap items-center justify-between gap-3 rounded border border-l-4 bg-white px-5 py-4 ${tone}`}>
      <div>
        <div className="font-display text-sm font-semibold text-navy">{title}</div>
        <p className="mt-1.5 text-sm text-steel">{body}</p>
        {extra && <div className="mt-1.5 font-mono text-[11px] text-steel">{extra}</div>}
        {s.activation_overdue && <p className="mt-1.5 text-sm text-red">{t("onboarding.panelOverdue")}</p>}
      </div>
      {action && (
        <Link to={action.href} className="rounded bg-amber px-4 py-2 text-sm font-semibold text-white hover:bg-amber-dark">
          {action.label}
        </Link>
      )}
    </div>
  );
}

export function ContractorStatusPage() {
  return (
    <>
      <div className="mx-auto max-w-3xl px-5 pt-8">
        <OnboardingPanel />
      </div>
      <DocumentStatus />
    </>
  );
}

function DocumentStatus() {
  const { t, language } = useI18n();
  const { data: profile } = useQuery({
    queryKey: ["contractor-profile"],
    queryFn: () => apiFetch<ContractorProfile>("/contractor/profile"),
  });
  const { data: docs } = useQuery({
    queryKey: ["contractor-documents"],
    queryFn: () => apiFetch<ContractorDocument[]>("/contractor/documents"),
    enabled: !!profile,
  });

  if (!profile) return <PageLoading />;

  if (profile.is_suspended) {
    return (
      <main className="max-w-2xl mx-auto px-5 py-8">
        <div className="bg-white border border-red border-l-4 rounded px-5 py-4">
          <div className="font-display font-semibold text-navy">{t("contractor.status.suspendedTitle")}</div>
          <p className="text-sm text-steel mt-1.5">{t("contractor.status.suspendedBody")}</p>
        </div>
      </main>
    );
  }

  if (profile.verification_status === "approved") {
    return (
      <main className="max-w-2xl mx-auto px-5 py-8">
        <div className="bg-white border border-green border-l-4 rounded px-5 py-4">
          <div className="font-display font-semibold text-navy">{t("contractor.status.approvedTitle")}</div>
          <p className="text-sm text-steel mt-1.5">{t("contractor.status.approvedBody")}</p>
        </div>
      </main>
    );
  }

  const bannerClasses = profile.verification_status === "changes_requested" ? "border-red" : "border-amber";
  const bannerTitle =
    profile.verification_status === "changes_requested"
      ? t("contractor.status.changesRequestedTitle")
      : t("contractor.status.underReviewTitle");

  return (
    <main className="max-w-3xl mx-auto px-5 py-8">
      <span className="text-xs font-semibold uppercase tracking-widest text-amber-dark block mb-1">{t("contractor.status.eyebrow")}</span>
      <h1 className="font-display text-3xl font-bold text-navy mb-1">{t("contractor.status.heading")}</h1>
      <p className="text-[13.5px] text-steel mb-6">{profile.company_name}</p>

      <div className={`bg-white border border-l-4 rounded px-5 py-4 mb-6 flex items-center justify-between flex-wrap gap-3 ${bannerClasses}`}>
        <div>
          <div className="font-display font-semibold text-navy text-sm">{bannerTitle}</div>
          <div className="font-mono text-[11px] text-steel mt-1">
            {t("contractor.status.submittedOn")} {formatDate(profile.created_at, language)}
          </div>
        </div>
        <span className={`font-mono text-[10px] uppercase px-2.5 py-1 rounded-full ${statusBadge(profile.verification_status === "pending_review" ? "pending" : "rejected")}`}>
          {profile.verification_status === "pending_review" ? t("contractor.status.pending") : t("contractor.status.actionNeeded")}
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border bg-white shadow-sm">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className="text-xs font-semibold uppercase tracking-wide text-steel text-left border-b border-border py-2">{t("contractor.status.document")}</th>
            <th className="text-xs font-semibold uppercase tracking-wide text-steel text-left border-b border-border py-2">{t("contractor.status.statusCol")}</th>
            <th className="border-b border-border py-2"></th>
          </tr>
        </thead>
        <tbody>
          {docs?.map((d) => (
            <tr key={d.id} className="border-b border-border">
              <td className="py-3.5">
                <div className="font-display font-semibold text-[13.5px]">{d.requirement_name}</div>
                <span className="font-mono text-[9.5px] uppercase text-steel-light">
                  {d.requirement_is_required ? t("contractor.status.required") : t("contractor.status.optional")}
                </span>
                {d.status === "rejected" && d.admin_note && (
                  <div className="mt-1.5 text-[11.5px] text-red bg-red-tint px-2.5 py-1.5 rounded font-mono">
                    {t("contractor.status.adminNote")} {d.admin_note}
                  </div>
                )}
              </td>
              <td className="py-3.5">
                <span className={`font-mono text-[10px] uppercase px-2 py-1 rounded-full ${statusBadge(d.status)}`}>{d.status.replace("_", " ")}</span>
              </td>
              <td className="py-3.5">
                {(d.status === "not_submitted" || d.status === "rejected") && (
                  <a href="/contractor/verify" className="border border-navy text-navy hover:bg-navy hover:text-white text-xs font-semibold rounded-md px-3 py-1.5">
                    {d.status === "rejected" ? t("contractor.status.reupload") : t("contractor.status.upload")}
                  </a>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>

      <p className="text-xs text-steel-light mt-4">{t("contractor.status.footerNote")}</p>
    </main>
  );
}
