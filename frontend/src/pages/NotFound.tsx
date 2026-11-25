import { Link } from "react-router-dom";
import { useI18n } from "@/i18n/I18nContext";

export function NotFoundPage() {
  const { t } = useI18n();
  return (
    <main className="max-w-md mx-auto px-5 py-20 text-center">
      <span className="text-xs font-semibold uppercase tracking-widest text-amber-dark block mb-2">404</span>
      <h1 className="font-display text-3xl font-bold text-navy mb-2">{t("errors.notFoundTitle")}</h1>
      <p className="text-sm text-steel mb-6">{t("errors.notFoundBody")}</p>
      <Link to="/" className="inline-block bg-navy hover:bg-navy-deep text-white text-sm font-semibold rounded px-5 py-2.5">
        {t("errors.goHome")}
      </Link>
    </main>
  );
}
