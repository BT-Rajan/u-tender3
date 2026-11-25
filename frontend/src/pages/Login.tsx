import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { useI18n } from "@/i18n/I18nContext";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { ApiError } from "@/api/client";

const INPUT =
  "w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20";

export function LoginPage() {
  const { login } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { notice?: string } };
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      await login(form.get("email") as string, form.get("password") as string);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("auth.login.genericError"));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid min-h-screen bg-paper text-ink md:grid-cols-2">
      <aside className="hidden flex-col justify-between bg-navy p-12 text-white md:flex">
        <Link to="/" className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded bg-white font-display text-lg font-bold text-navy">
            U
          </span>
          <span className="font-display text-base font-bold tracking-wide">U-TENDER</span>
        </Link>
        <div>
          <p className="font-display text-3xl font-bold leading-tight">{t("brand.tagline")}</p>
          <p className="mt-4 max-w-md text-white/75">{t("home.heroBody")}</p>
        </div>
        <p className="text-xs uppercase tracking-widest text-white/50">U-TENDER</p>
      </aside>

      <main className="flex items-center justify-center px-5 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center justify-between md:hidden">
            <Link to="/" className="font-display text-lg font-bold text-navy">
              U-TENDER
            </Link>
            <LanguageSwitcher />
          </div>
          <div className="mb-6 hidden justify-end md:flex">
            <LanguageSwitcher />
          </div>

          <div className="rounded border border-border bg-white p-8 shadow-sm">
            <h1 className="font-display text-2xl font-bold text-navy">{t("auth.login.heading")}</h1>

            {location.state?.notice && (
              <p role="status" className="mb-4 mt-4 rounded border border-blue bg-blue-tint px-3.5 py-2.5 text-sm text-blue">
                {location.state.notice}
              </p>
            )}
            {error && (
              <p role="alert" className="mb-4 mt-4 rounded border border-red bg-red-tint px-3.5 py-2.5 text-sm text-red">
                {error}
              </p>
            )}

            <form onSubmit={handleSubmit} className="mt-6 grid gap-5">
              <div>
                <label htmlFor="login-email" className="mb-1.5 block text-sm font-medium text-ink">
                  {t("auth.login.email")}
                </label>
                <input id="login-email" type="email" name="email" autoComplete="email" required className={INPUT} />
              </div>
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label htmlFor="login-password" className="text-sm font-medium text-ink">
                    {t("auth.login.password")}
                  </label>
                  <Link to="/forgot-password" className="text-xs font-medium text-navy hover:underline">
                    {t("auth.login.forgotPassword")}
                  </Link>
                </div>
                <input
                  id="login-password"
                  type="password"
                  name="password"
                  autoComplete="current-password"
                  required
                  className={INPUT}
                />
              </div>
              <button
                type="submit"
                disabled={pending}
                className="rounded bg-amber px-5 py-3 text-sm font-semibold text-white hover:bg-amber-dark disabled:opacity-60"
              >
                {pending ? t("auth.login.submitting") : t("auth.login.submit")}
              </button>
            </form>
          </div>

          <p className="mt-6 text-center text-sm text-steel">
            {t("auth.login.noAccount")}{" "}
            <Link to="/signup" className="font-semibold text-navy hover:underline">
              {t("auth.login.signupLink")}
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}
