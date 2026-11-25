import { Link, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthContext";
import { useI18n } from "@/i18n/I18nContext";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { QrCode } from "@/components/QrCode";
import { whatsappLink } from "@/components/WhatsAppCard";
import { apiFetch } from "@/api/client";

interface PublicStats {
  open_tenders: number;
  verified_contractors: number;
  awarded_projects: number;
  total_awarded_value: string;
}

function StatTile({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded border border-white/15 bg-white/5 px-5 py-4">
      <div className="font-display text-3xl font-bold leading-none text-white">{value}</div>
      <div className="mt-2 text-xs uppercase tracking-wide text-white/70">{label}</div>
    </div>
  );
}

function FeatureCard({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded border border-border bg-white p-6">
      <h3 className="font-display text-lg font-semibold text-navy">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-steel">{body}</p>
    </div>
  );
}

export function HomePage() {
  const { user, loading } = useAuth();
  const { t, language } = useI18n();

  const { data: cms } = useQuery({
    queryKey: ["public-cms", language],
    queryFn: () => apiFetch<Record<string, string>>(`/public/cms?language=${language}`),
    enabled: !user,
  });
  const { data: stats } = useQuery({
    queryKey: ["public-stats"],
    queryFn: () => apiFetch<PublicStats>("/public/stats"),
    enabled: !user,
  });

  if (loading) return null;

  if (user) {
    if (user.role === "admin") return <Navigate to="/admin/requirements" replace />;
    if (user.role === "owner") return <Navigate to="/owner/dashboard" replace />;
    // The contractor dashboard branches on marketplace_status itself, so every
    // state (documents incomplete, pending, payment required, active, suspended) lands there.
    return <Navigate to="/contractor/dashboard" replace />;
  }

  const waHref = whatsappLink(import.meta.env.VITE_WHATSAPP_NUMBER);
  const steps = [t("home.step1"), t("home.step2"), t("home.step3")];

  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-2 px-4 sm:px-5">
          <div className="flex items-center gap-2.5 sm:gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-navy font-display text-lg font-bold text-white">
              U
            </div>
            <div>
              <div className="whitespace-nowrap font-display text-base font-bold leading-none text-navy">U-TENDER</div>
              <div className="mt-1 hidden text-[10px] uppercase tracking-widest text-steel sm:block">{t("brand.tagline")}</div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-4">
            <LanguageSwitcher />
            <Link to="/login" className="whitespace-nowrap text-xs font-semibold text-navy hover:underline sm:text-sm">
              {t("home.login")}
            </Link>
            <Link to="/signup" className="whitespace-nowrap rounded bg-amber px-3 py-2 text-xs font-semibold text-white hover:bg-amber-dark sm:px-4 sm:text-sm">
              {t("home.signup")}
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section className="bg-navy text-white">
          <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 py-20 md:grid-cols-2">
            <div>
              <h1 className="font-display text-3xl font-bold leading-tight sm:text-5xl">
                {cms?.hero_heading ?? t("home.heroTitle")}
              </h1>
              <p className="mt-5 text-base leading-relaxed text-white/80">
                {cms?.hero_subheading ?? t("home.heroBody")}
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/signup" className="rounded bg-amber px-6 py-3 text-sm font-semibold text-white hover:bg-amber-dark">
                  {t("home.signup")}
                </Link>
                <Link
                  to="/login"
                  className="rounded border border-white/40 px-6 py-3 text-sm font-semibold text-white hover:bg-white hover:text-navy"
                >
                  {t("home.login")}
                </Link>
              </div>
            </div>
            {stats && (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 md:grid-cols-1">
                <StatTile value={String(stats.open_tenders)} label={t("home.statOpen")} />
                <StatTile value={String(stats.verified_contractors)} label={t("home.statContractors")} />
                <StatTile value={String(stats.awarded_projects)} label={t("home.statAwarded")} />
              </div>
            )}
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-5 py-16">
          <h2 className="font-display text-2xl font-bold text-navy">{t("home.featuresTitle")}</h2>
          <div className="mt-8 grid gap-5 md:grid-cols-3">
            <FeatureCard title={t("home.feature1Title")} body={t("home.feature1Body")} />
            <FeatureCard title={t("home.feature2Title")} body={t("home.feature2Body")} />
            <FeatureCard title={t("home.feature3Title")} body={t("home.feature3Body")} />
          </div>
        </section>

        <section className="border-y border-border bg-white">
          <div className="mx-auto max-w-6xl px-5 py-16">
            <h2 className="font-display text-2xl font-bold text-navy">{t("home.howTitle")}</h2>
            <ol className="mt-8 grid gap-5 md:grid-cols-3">
              {steps.map((step, index) => (
                <li key={step} className="flex items-start gap-4 rounded border border-border p-5">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy text-sm font-bold text-white">
                    {index + 1}
                  </span>
                  <span className="font-semibold text-ink">{step}</span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {waHref && (
          <section className="mx-auto max-w-6xl px-5 py-16">
            <div className="grid items-center gap-10 rounded border border-border bg-white p-8 md:grid-cols-2">
              <div>
                <h2 className="font-display text-2xl font-bold text-navy">{t("home.whatsappTitle")}</h2>
                <p className="mt-3 leading-relaxed text-steel">{t("home.whatsappBody")}</p>
                <a
                  href={waHref}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-6 inline-block rounded bg-green px-6 py-3 text-sm font-semibold text-white hover:opacity-90"
                >
                  {t("whatsapp.cta")}
                </a>
              </div>
              <div className="flex justify-center md:justify-end">
                <QrCode value={waHref} alt={t("home.qrAlt")} />
              </div>
            </div>
          </section>
        )}

        {(cms?.how_it_works_title || cms?.how_it_works_body) && (
          <section className="mx-auto max-w-3xl px-5 pb-16">
            <div className="rounded border border-border bg-white p-7">
              <h2 className="font-display text-xl font-semibold text-navy">{cms.how_it_works_title}</h2>
              <p className="mt-3 text-sm leading-relaxed text-steel">{cms.how_it_works_body}</p>
            </div>
          </section>
        )}
      </main>

      <footer className="border-t border-border bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-8 text-sm text-steel">
          <span className="font-display font-semibold text-navy">U-TENDER</span>
          <span>{t("brand.tagline")}</span>
        </div>
      </footer>
    </div>
  );
}
