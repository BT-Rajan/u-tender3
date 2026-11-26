import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useI18n } from "@/i18n/I18nContext";
import { errorText } from "@/lib/errors";

const INPUT =
  "w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20";

// Two steps: the email asks for a code, which is sent on WhatsApp to the number on the account;
// then the code and a new password set it. The first step answers the same for every email.
export function ForgotPasswordPage() {
  const { t } = useI18n();
  const [email, setEmail] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestCode = useMutation({
    mutationFn: (value: string) => apiFetch("/auth/password-reset/request", { method: "POST", body: { email: value } }),
    onSuccess: (_data, value) => {
      setError(null);
      setEmail(value);
    },
    onError: (err) => setError(errorText(err, t("onboarding.forgotError"))),
  });

  const confirm = useMutation({
    mutationFn: (values: { code: string; new_password: string }) =>
      apiFetch("/auth/password-reset/confirm", { method: "POST", body: { email, ...values } }),
    onSuccess: () => {
      setError(null);
      setDone(true);
    },
    onError: (err) => setError(errorText(err, t("onboarding.forgotError"))),
  });

  function handleEmail(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    requestCode.mutate(String(new FormData(e.currentTarget).get("email") ?? "").trim());
  }

  function handleCode(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    confirm.mutate({
      code: String(form.get("code") ?? "").trim(),
      new_password: String(form.get("new_password") ?? ""),
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

        <div className="rounded border border-border bg-white p-8 shadow-sm">
          <h1 className="font-display text-2xl font-bold text-navy">{t("auth.forgotPassword.heading")}</h1>
          {!done && email === null && <p className="mt-2 text-sm leading-relaxed text-steel">{t("auth.forgotPassword.description")}</p>}

          {error && (
            <p role="alert" className="mb-4 mt-5 rounded border border-red bg-red-tint px-3.5 py-2.5 text-sm text-red">
              {error}
            </p>
          )}

          {done ? (
            <p role="status" className="mt-5 rounded border border-blue bg-blue-tint px-3.5 py-2.5 text-sm text-blue">
              {t("onboarding.forgotDone")}
            </p>
          ) : email === null ? (
            <form onSubmit={handleEmail} className="mt-6 grid gap-5">
              <div>
                <label htmlFor="forgot-email" className="mb-1.5 block text-sm font-medium text-ink">
                  {t("auth.forgotPassword.email")}
                </label>
                <input id="forgot-email" type="email" name="email" autoComplete="email" required className={INPUT} />
              </div>
              <button
                type="submit"
                disabled={requestCode.isPending}
                className="rounded bg-amber px-5 py-3 text-sm font-semibold text-white hover:bg-amber-dark disabled:opacity-60"
              >
                {requestCode.isPending ? t("auth.forgotPassword.submitting") : t("auth.forgotPassword.submit")}
              </button>
            </form>
          ) : (
            <form onSubmit={handleCode} className="mt-6 grid gap-5">
              <p role="status" className="rounded border border-blue bg-blue-tint px-3.5 py-2.5 text-sm text-blue">
                {t("onboarding.forgotCodeSent")}
              </p>
              <div>
                <label htmlFor="reset-code" className="mb-1.5 block text-sm font-medium text-ink">
                  {t("onboarding.forgotCode")}
                </label>
                <input id="reset-code" name="code" inputMode="numeric" autoComplete="one-time-code" required minLength={4} maxLength={10} className={INPUT} />
              </div>
              <div>
                <label htmlFor="reset-password" className="mb-1.5 block text-sm font-medium text-ink">
                  {t("onboarding.forgotNewPassword")}
                </label>
                <input id="reset-password" name="new_password" type="password" autoComplete="new-password" required minLength={8} className={INPUT} />
              </div>
              <button
                type="submit"
                disabled={confirm.isPending}
                className="rounded bg-amber px-5 py-3 text-sm font-semibold text-white hover:bg-amber-dark disabled:opacity-60"
              >
                {confirm.isPending ? t("onboarding.forgotSaving") : t("onboarding.forgotConfirm")}
              </button>
              <button type="button" onClick={() => setEmail(null)} className="text-sm font-semibold text-navy hover:underline">
                {t("onboarding.useAnotherEmail")}
              </button>
            </form>
          )}
        </div>

        <p className="mt-6 text-center text-sm text-steel">
          <Link to="/login" className="font-semibold text-navy hover:underline">
            {t("auth.forgotPassword.backToLogin")}
          </Link>
        </p>
      </div>
    </div>
  );
}
