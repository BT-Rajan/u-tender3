import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { AppHeader } from "@/components/AppHeader";

interface NavItem {
  to: string;
  label: string;
  end?: boolean;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

// The admin menu, grouped by what the admin is doing. Routes are unchanged; only the menu moved.
export const ADMIN_NAV: NavGroup[] = [
  {
    label: "Reports",
    items: [
      { to: "/admin/reports", label: "Overview", end: true },
      { to: "/admin/reports/tenders", label: "Tenders" },
      { to: "/admin/reports/billing", label: "Billing" },
      { to: "/admin/reports/activations", label: "Activations" },
    ],
  },
  {
    label: "Users",
    items: [
      { to: "/admin/users", label: "All users" },
      { to: "/admin/contractors", label: "Contractors" },
      { to: "/admin/owners", label: "Owners" },
    ],
  },
  {
    label: "Billing",
    items: [
      { to: "/admin/activations", label: "Activation queue" },
      { to: "/admin/plans", label: "Plans" },
      { to: "/admin/payment-setup", label: "Payment setup" },
    ],
  },
  {
    label: "Verification",
    items: [
      { to: "/admin/review", label: "Review queue" },
      { to: "/admin/requirements", label: "Requirements" },
    ],
  },
  {
    label: "Tenders",
    items: [
      { to: "/admin/projects", label: "Projects" },
      { to: "/admin/offers", label: "Offers" },
    ],
  },
  {
    label: "Content",
    items: [{ to: "/admin/cms", label: "Website content" }],
  },
];

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block rounded px-3 py-2 text-sm font-medium transition-colors ${
    isActive ? "bg-navy text-white" : "text-steel hover:bg-paper hover:text-navy"
  }`;

export function AdminLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();

  // On a phone the menu is a panel over the page; close it once the admin has picked a screen.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  return (
    <div className="min-h-screen bg-paper text-ink">
      <AppHeader roleLabel="Site Admin" homeHref="/admin/reports" />

      <div className="flex flex-col lg:flex-row">
        <div className="border-b border-border bg-white px-5 py-3 lg:hidden">
          <button
            type="button"
            aria-expanded={menuOpen}
            aria-controls="admin-menu"
            onClick={() => setMenuOpen((open) => !open)}
            className="rounded border border-navy px-4 py-2 text-sm font-semibold text-navy"
          >
            {menuOpen ? "Close menu" : "Menu"}
          </button>
        </div>

        <aside
          id="admin-menu"
          className={`${menuOpen ? "block" : "hidden"} border-b border-border bg-white px-4 py-5 lg:sticky lg:top-0 lg:block lg:h-screen lg:w-60 lg:shrink-0 lg:overflow-y-auto lg:border-b-0 lg:border-r`}
        >
          <nav aria-label="Admin" className="grid gap-6">
            {ADMIN_NAV.map((group) => (
              <div key={group.label}>
                <div className="mb-2 px-3 font-mono text-[10px] uppercase tracking-widest text-steel-light">{group.label}</div>
                <div className="grid gap-1">
                  {group.items.map((item) => (
                    <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
                      {item.label}
                    </NavLink>
                  ))}
                </div>
              </div>
            ))}
          </nav>
        </aside>

        <div className="min-w-0 flex-1 px-5 py-8">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
