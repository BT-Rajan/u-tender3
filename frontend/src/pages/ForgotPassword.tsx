import { useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, ApiError } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

const INPUT =
  "w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20";

export function ForgotPasswordPage() {
  const { t } = useI18n();
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      await apiFetch("/auth/forgot-password", { method: "POST", body: { email: form.get("email") } });
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("auth.forgotPassword.sent"));
    } finally {
      setPending(false);
    }
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
          <p className="mt-2 text-sm leading-relaxed text-steel">{t("auth.forgotPassword.description")}</p>

          {error && (
            <p role="alert" className="mb-4 mt-5 rounded border border-red bg-red-tint px-3.5 py-2.5 text-sm text-red">
              {error}
            </p>
          )}

          {sent ? (
            <p role="status" className="mt-5 rounded border border-blue bg-blue-tint px-3.5 py-2.5 text-sm text-blue">
              {t("auth.forgotPassword.sent")}
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="mt-6 grid gap-5">
              <div>
                <label htmlFor="forgot-email" className="mb-1.5 block text-sm font-medium text-ink">
                  {t("auth.forgotPassword.email")}
                </label>
                <input id="forgot-email" type="email" name="email" autoComplete="email" required className={INPUT} />
              </div>
              <button
                type="submit"
                disabled={pending}
                className="rounded bg-amber px-5 py-3 text-sm font-semibold text-white hover:bg-amber-dark disabled:opacity-60"
              >
                {pending ? t("auth.forgotPassword.submitting") : t("auth.forgotPassword.submit")}
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
