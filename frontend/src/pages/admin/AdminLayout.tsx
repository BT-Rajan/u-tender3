import { NavLink, Outlet } from "react-router-dom";
import { AppHeader } from "@/components/AppHeader";
import { useI18n } from "@/i18n/I18nContext";

const tabClass = ({ isActive }: { isActive: boolean }) =>
  `whitespace-nowrap border-b-2 px-1 pb-3 pt-2 text-sm font-semibold transition-colors ${
    isActive ? "border-navy text-navy" : "border-transparent text-steel hover:text-navy"
  }`;

export function AdminLayout() {
  const { t } = useI18n();
  return (
    <div className="min-h-screen bg-paper text-ink">
      <AppHeader roleLabel="Site Admin" homeHref="/admin/requirements" />
      <nav className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-6xl gap-6 overflow-x-auto px-5">
          <NavLink to="/admin/requirements" className={tabClass}>
            {t("admin.nav.requirements")}
          </NavLink>
          <NavLink to="/admin/review" className={tabClass}>
            {t("admin.nav.review")}
          </NavLink>
          <NavLink to="/admin/contractors" className={tabClass}>
            {t("admin.nav.contractors")}
          </NavLink>
          <NavLink to="/admin/owners" className={tabClass}>
            {t("admin.nav.owners")}
          </NavLink>
          <NavLink to="/admin/projects" className={tabClass}>
            {t("admin.nav.projects")}
          </NavLink>
          <NavLink to="/admin/offers" className={tabClass}>
            {t("admin.nav.offers")}
          </NavLink>
          <NavLink to="/admin/activations" className={tabClass}>
            Activations
          </NavLink>
          <NavLink to="/admin/plans" className={tabClass}>
            Plans
          </NavLink>
          <NavLink to="/admin/payment-setup" className={tabClass}>
            Payment setup
          </NavLink>
          <NavLink to="/admin/cms" className={tabClass}>
            {t("admin.nav.cms")}
          </NavLink>
        </div>
      </nav>
      <div className="mx-auto max-w-6xl px-5 py-8">
        <Outlet />
      </div>
    </div>
  );
}
