import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { ErrorBanner } from "@/components/ErrorBanner";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useI18n } from "@/i18n/I18nContext";
import { errorText } from "@/lib/errors";

const INPUT =
  "w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20";

// A contractor who signed up on WhatsApp opens the 24-hour link and adds an email and password here.
export function ContractorJoinPage() {
  const { t } = useI18n();
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [error, setError] = useState<string | null>(null);

  const finish = useMutation({
    mutationFn: (values: { email: string; password: string }) =>
      apiFetch("/auth/contractor/complete-invite", { method: "POST", body: { token, ...values } }),
    onSuccess: async () => {
      await refresh();
      navigate("/contractor/onboarding");
    },
    onError: (err) => setError(errorText(err, t("onboarding.joinError"))),
  });

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    finish.mutate({
      email: String(form.get("email") ?? "").trim(),
      password: String(form.get("password") ?? ""),
    });
  }

  return (
    <div className="min-h-screen bg-paper px-5 py-12 text-ink">
      <div className="mx-auto max-w-sm">
        <div className="mb-8 flex items-center justify-between">
          <Link to="/" className="font-display text-lg font-bold text-navy">
            U-TENDER
          </Link>
          <LanguageSwitcher />
        </div>

        <h1 className="font-display text-2xl font-bold text-navy">{t("onboarding.joinHeading")}</h1>
        {token ? (
          <p className="mt-2 text-sm leading-relaxed text-steel">{t("onboarding.joinIntro")}</p>
        ) : (
          <p className="mt-2 text-sm leading-relaxed text-red">{t("onboarding.joinMissing")}</p>
        )}

        <div className="mt-5">
          <ErrorBanner message={error} />
        </div>

        {token && (
          <form onSubmit={handleSubmit} className="mt-4 grid gap-4">
            <div>
              <label htmlFor="join-email" className="mb-1.5 block text-sm font-medium text-ink">
                {t("onboarding.email")}
              </label>
              <input id="join-email" name="email" type="email" autoComplete="email" required className={INPUT} />
            </div>
            <div>
              <label htmlFor="join-password" className="mb-1.5 block text-sm font-medium text-ink">
                {t("onboarding.password")}
              </label>
              <input id="join-password" name="password" type="password" autoComplete="new-password" required minLength={8} className={INPUT} />
              <p className="mt-1 text-xs text-steel-light">{t("onboarding.passwordHint")}</p>
            </div>
            <button
              type="submit"
              disabled={finish.isPending}
              className="rounded bg-amber px-5 py-3 text-sm font-semibold text-white hover:bg-amber-dark disabled:opacity-60"
            >
              {finish.isPending ? t("onboarding.joinSaving") : t("onboarding.joinSubmit")}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
