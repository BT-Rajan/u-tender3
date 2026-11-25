import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { useI18n } from "@/i18n/I18nContext";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { NotificationBell } from "@/components/NotificationBell";

export function AppHeader({ roleLabel, homeHref }: { roleLabel: string; homeHref: string }) {
  const { logout } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/");
  };

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-5">
        <Link to={homeHref} className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-navy font-display text-lg font-bold text-white">
            U
          </div>
          <div>
            <div className="font-display text-base font-bold leading-none text-navy">U-TENDER</div>
            <div className="mt-1 hidden text-[10px] uppercase tracking-widest text-steel sm:block">{t("brand.tagline")}</div>
          </div>
        </Link>

        <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
          <NotificationBell />
          <LanguageSwitcher />
          <span className="whitespace-nowrap rounded-full bg-paper px-3 py-1 text-xs font-semibold text-steel">{roleLabel}</span>
          <Link to="/account" className="whitespace-nowrap text-sm font-medium text-navy hover:underline">
            {t("header.account")}
          </Link>
          <button
            type="button"
            onClick={() => handleLogout()}
            className="whitespace-nowrap text-sm font-medium text-steel hover:text-navy hover:underline"
          >
            {t("header.logOut")}
          </button>
        </div>
      </div>
    </header>
  );
}
