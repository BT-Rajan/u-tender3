import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { ErrorBanner } from "@/components/ErrorBanner";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useI18n } from "@/i18n/I18nContext";
import { errorText } from "@/lib/errors";

const INPUT =
  "w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20";

// Contractors sign up with a code sent to their WhatsApp number: step 1 asks for the number,
// step 2 takes the code plus the login details.
export function ContractorSignupPage() {
  const { t } = useI18n();
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const requestCode = useMutation({
    mutationFn: (phone: string) => apiFetch("/auth/contractor/code/request", { method: "POST", body: { phone } }),
    onSuccess: (_data, phone) => {
      setError(null);
      setSentTo(phone);
    },
    onError: (err) => setError(errorText(err, t("onboarding.signupError"))),
  });

  const createAccount = useMutation({
    mutationFn: (values: { code: string; email: string; password: string; full_name: string; company_name: string }) =>
      apiFetch("/auth/contractor/signup", { method: "POST", body: { phone: sentTo, ...values } }),
    onSuccess: async () => {
      await refresh();
      navigate("/contractor/onboarding");
    },
    onError: (err) => setError(errorText(err, t("onboarding.signupError"))),
  });

  function handlePhone(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const phone = String(new FormData(e.currentTarget).get("phone") ?? "");
    requestCode.mutate(phone);
  }

  function handleAccount(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    createAccount.mutate({
      code: String(form.get("code") ?? "").trim(),
      email: String(form.get("email") ?? "").trim(),
      password: String(form.get("password") ?? ""),
      full_name: String(form.get("full_name") ?? "").trim(),
      company_name: String(form.get("company_name") ?? "").trim(),
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

        <span className="block text-xs font-semibold uppercase tracking-widest text-amber-dark">{t("onboarding.signupEyebrow")}</span>
        <h1 className="mt-1 font-display text-2xl font-bold text-navy">{t("onboarding.signupHeading")}</h1>
        <p className="mt-2 text-sm leading-relaxed text-steel">{t("onboarding.signupIntro")}</p>

        <div className="mt-6">
          <ErrorBanner message={error} />
        </div>

        {sentTo === null ? (
          <form onSubmit={handlePhone} className="mt-4 grid gap-4">
            <div>
              <label htmlFor="signup-phone" className="mb-1.5 block text-sm font-medium text-ink">
                {t("onboarding.phone")}
              </label>
              <input id="signup-phone" name="phone" type="tel" inputMode="numeric" required className={INPUT} />
              <p className="mt-1 text-xs text-steel-light">{t("onboarding.phoneHint")}</p>
            </div>
            <button
              type="submit"
              disabled={requestCode.isPending}
              className="rounded bg-amber px-5 py-3 text-sm font-semibold text-white hover:bg-amber-dark disabled:opacity-60"
            >
              {requestCode.isPending ? t("onboarding.sending") : t("onboarding.sendCode")}
            </button>
          </form>
        ) : (
          <form onSubmit={handleAccount} className="mt-4 grid gap-4">
            <p role="status" className="rounded border border-blue bg-blue-tint px-3.5 py-2.5 text-sm text-blue">
              {t("onboarding.codeSent")}
            </p>
            <div>
              <label htmlFor="signup-code" className="mb-1.5 block text-sm font-medium text-ink">
                {t("onboarding.code")}
              </label>
              <input id="signup-code" name="code" inputMode="numeric" autoComplete="one-time-code" required minLength={4} maxLength={10} className={INPUT} />
            </div>
            <div>
              <label htmlFor="signup-name" className="mb-1.5 block text-sm font-medium text-ink">
                {t("onboarding.fullName")}
              </label>
              <input id="signup-name" name="full_name" required minLength={2} className={INPUT} />
            </div>
            <div>
              <label htmlFor="signup-company" className="mb-1.5 block text-sm font-medium text-ink">
                {t("onboarding.company")}
              </label>
              <input id="signup-company" name="company_name" required minLength={2} className={INPUT} />
            </div>
            <div>
              <label htmlFor="signup-email" className="mb-1.5 block text-sm font-medium text-ink">
                {t("onboarding.email")}
              </label>
              <input id="signup-email" name="email" type="email" autoComplete="email" required className={INPUT} />
            </div>
            <div>
              <label htmlFor="signup-password" className="mb-1.5 block text-sm font-medium text-ink">
                {t("onboarding.password")}
              </label>
              <input id="signup-password" name="password" type="password" autoComplete="new-password" required minLength={8} className={INPUT} />
              <p className="mt-1 text-xs text-steel-light">{t("onboarding.passwordHint")}</p>
            </div>
            <button
              type="submit"
              disabled={createAccount.isPending}
              className="rounded bg-amber px-5 py-3 text-sm font-semibold text-white hover:bg-amber-dark disabled:opacity-60"
            >
              {createAccount.isPending ? t("onboarding.creating") : t("onboarding.createAccount")}
            </button>
            <button type="button" onClick={() => setSentTo(null)} className="text-sm font-semibold text-navy hover:underline">
              {t("onboarding.changeNumber")}
            </button>
          </form>
        )}

        <p className="mt-6 text-center text-sm text-steel">
          {t("onboarding.haveAccount")}{" "}
          <Link to="/login" className="font-semibold text-navy hover:underline">
            {t("onboarding.logIn")}
          </Link>
        </p>
      </div>
    </div>
  );
}
