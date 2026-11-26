import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { AdminUserDetail, AdminUserList } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { ErrorBanner } from "@/components/ErrorBanner";
import { PageLoading } from "@/components/PageLoading";
import { QueryError } from "@/components/QueryError";
import { errorText } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";

const PAGE_SIZE = 25;

const INPUT =
  "rounded border border-border bg-white px-3 py-2 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20";

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "Any status" },
  { value: "suspended", label: "Suspended" },
  { value: "verified_active", label: "Verified & active" },
  { value: "payment_required", label: "Payment required" },
  { value: "documents_incomplete", label: "Documents incomplete" },
  { value: "submitted_for_review", label: "Submitted for review" },
  { value: "changes_requested", label: "Changes requested" },
];

const STATUS_BADGE: Record<string, string> = {
  suspended: "bg-red-tint text-red",
  verified_active: "bg-green-tint text-green",
  payment_required: "bg-amber/15 text-amber-dark",
  submitted_for_review: "bg-amber/15 text-amber-dark",
  changes_requested: "bg-red-tint text-red",
  documents_incomplete: "bg-blue-tint text-steel",
  admin: "bg-blue-tint text-blue",
  no_profile: "bg-blue-tint text-steel",
};

const ROLE_BADGE: Record<string, string> = {
  owner: "bg-blue-tint text-blue",
  contractor: "bg-amber/15 text-amber-dark",
  admin: "bg-navy text-white",
};

function label(value: string) {
  return value.replace(/_/g, " ");
}

// Where an account's role-specific page lives, when it has one.
function rolePage(role: string, id: string): string | null {
  if (role === "contractor") return `/admin/contractors/${id}`;
  if (role === "owner") return `/admin/owners/${id}`;
  return null;
}

export function AdminUsersPage() {
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);

  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  if (search) params.set("q", search);
  if (role) params.set("role", role);
  if (status) params.set("status", status);

  const { data, isError, isFetching, refetch } = useQuery({
    queryKey: ["admin-users", search, role, status, offset],
    queryFn: () => apiFetch<AdminUserList>(`/admin/users?${params.toString()}`),
    placeholderData: keepPreviousData,
  });

  const from = data && data.total > 0 ? data.offset + 1 : 0;
  const to = data ? Math.min(data.offset + data.items.length, data.total) : 0;

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <span className="mb-1 block text-xs font-semibold uppercase tracking-widest text-amber-dark">Admin · Users</span>
        <h1 className="mb-1 font-display text-3xl font-bold text-navy">All users</h1>
        <p className="text-[13.5px] text-steel">Every owner, contractor and admin account. Search by name, email, phone or company.</p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setOffset(0);
          setSearch(q.trim());
        }}
        className="mb-4 grid gap-3 sm:grid-cols-[1fr_auto_auto_auto]"
      >
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, email, phone or company" aria-label="Search users" className={INPUT} />
        <select
          aria-label="Role"
          value={role}
          onChange={(e) => {
            setOffset(0);
            setRole(e.target.value);
          }}
          className={INPUT}
        >
          <option value="">Any role</option>
          <option value="owner">Owner</option>
          <option value="contractor">Contractor</option>
          <option value="admin">Admin</option>
        </select>
        <select
          aria-label="Status"
          value={status}
          onChange={(e) => {
            setOffset(0);
            setStatus(e.target.value);
          }}
          className={INPUT}
        >
          {STATUS_FILTERS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <button type="submit" className="rounded bg-navy px-4 py-2 text-sm font-semibold text-white">
          Search
        </button>
      </form>

      {isError ? (
        <QueryError onRetry={() => refetch()} />
      ) : !data ? (
        <PageLoading />
      ) : !data.items.length ? (
        <div className="rounded-lg border border-dashed border-border bg-white p-10 text-center text-sm text-steel">No users match these filters.</div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border bg-white shadow-sm">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th className="border-b border-border px-2.5 py-2 text-left text-xs font-semibold uppercase tracking-wide text-steel">Name</th>
                  <th className="border-b border-border px-2.5 py-2 text-left text-xs font-semibold uppercase tracking-wide text-steel">Contact</th>
                  <th className="border-b border-border px-2.5 py-2 text-left text-xs font-semibold uppercase tracking-wide text-steel">Role</th>
                  <th className="border-b border-border px-2.5 py-2 text-left text-xs font-semibold uppercase tracking-wide text-steel">Status</th>
                  <th className="border-b border-border px-2.5 py-2 text-left text-xs font-semibold uppercase tracking-wide text-steel">Joined</th>
                  <th className="border-b border-border px-2.5 py-2"></th>
                </tr>
              </thead>
              <tbody className={isFetching ? "opacity-60" : ""}>
                {data.items.map((user) => (
                  <tr key={user.id} className="border-b border-border">
                    <td className="px-2.5 py-3">
                      <div className="font-display text-[13.5px] font-semibold">{user.full_name || "No name"}</div>
                      {user.company_name && <div className="text-[11.5px] text-steel-light">{user.company_name}</div>}
                    </td>
                    <td className="px-2.5 py-3 text-[12.5px]">
                      <div>{user.email || "No email"}</div>
                      <div className="font-mono text-steel-light">{user.phone || ""}</div>
                    </td>
                    <td className="px-2.5 py-3">
                      <span className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase ${ROLE_BADGE[user.role] ?? ""}`}>{user.role}</span>
                    </td>
                    <td className="px-2.5 py-3">
                      <span className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase ${STATUS_BADGE[user.status] ?? "bg-blue-tint text-steel"}`}>
                        {label(user.status)}
                      </span>
                    </td>
                    <td className="px-2.5 py-3 font-mono text-[11.5px] text-steel">
                      {user.created_at ? formatDateTime(user.created_at, "en") : ""}
                    </td>
                    <td className="px-2.5 py-3 text-right">
                      <Link to={`/admin/users/${user.id}`} className="rounded-md border border-navy px-3 py-1.5 text-xs font-semibold text-navy hover:bg-navy hover:text-white">
                        Manage
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex items-center justify-between gap-3 text-sm text-steel">
            <span>
              {from}–{to} of {data.total}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                className="rounded border border-navy px-3 py-1.5 font-semibold text-navy disabled:opacity-40"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={offset + PAGE_SIZE >= data.total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
                className="rounded border border-navy px-3 py-1.5 font-semibold text-navy disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function AdminUserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user: me } = useAuth();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data: user, isError, refetch } = useQuery({
    queryKey: ["admin-user", id],
    queryFn: () => apiFetch<AdminUserDetail>(`/admin/users/${id}`),
    enabled: !!id,
  });

  const suspend = useMutation({
    mutationFn: (suspended: boolean) => apiFetch(`/admin/users/${id}/suspend`, { method: "POST", body: { suspended } }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-user", id] });
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (err) => setError(errorText(err, "Could not change this account.")),
  });

  if (isError) return <QueryError onRetry={() => refetch()} />;
  if (!user) return <PageLoading />;

  const isSelf = me?.id === user.id;
  const canSuspend = user.role !== "admin" && !isSelf;
  const detailPage = rolePage(user.role, user.id);

  function confirmToggle() {
    const next = !user!.is_suspended;
    const question = next
      ? `Suspend ${user!.full_name || user!.email || "this account"}? They lose access to the marketplace until you reactivate them.`
      : `Reactivate ${user!.full_name || user!.email || "this account"}?`;
    if (window.confirm(question)) suspend.mutate(next);
  }

  return (
    <div className="mx-auto max-w-4xl">
      <Link to="/admin/users" className="text-sm font-semibold text-navy hover:underline">
        ← All users
      </Link>

      <div className="mb-6 mt-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <span className="mb-1 block text-xs font-semibold uppercase tracking-widest text-amber-dark">Admin · User</span>
          <h1 className="font-display text-3xl font-bold text-navy">{user.full_name || user.email || "No name"}</h1>
          <p className="text-[13.5px] text-steel">
            {user.company_name ? `${user.company_name} · ` : ""}
            {user.email || "No email"}
            {user.phone ? ` · ${user.phone}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className={`rounded-full px-2.5 py-1 font-mono text-[10px] uppercase ${ROLE_BADGE[user.role] ?? ""}`}>{user.role}</span>
          <span className={`rounded-full px-2.5 py-1 font-mono text-[10px] uppercase ${STATUS_BADGE[user.status] ?? "bg-blue-tint text-steel"}`}>
            {label(user.status)}
          </span>
        </div>
      </div>

      <ErrorBanner message={error} />

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-lg border border-border bg-white px-5 py-5 shadow-sm">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-navy">Account</h2>
          <dl className="grid gap-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-steel">Joined</dt>
              <dd>{user.created_at ? formatDateTime(user.created_at, "en") : "-"}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-steel">Email verified</dt>
              <dd>{user.email_verified ? "Yes" : "No"}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-steel">Password login</dt>
              <dd>{user.can_log_in_with_password ? "Yes" : "WhatsApp only"}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-steel">Language</dt>
              <dd>{user.language}</dd>
            </div>
          </dl>

          <div className="mt-5 flex flex-wrap gap-2">
            {detailPage && (
              <Link to={detailPage} className="rounded border border-navy px-4 py-2 text-xs font-semibold text-navy hover:bg-navy hover:text-white">
                Open {user.role} record
              </Link>
            )}
            <Link to={`/admin/users/${user.id}/history`} className="rounded border border-navy px-4 py-2 text-xs font-semibold text-navy hover:bg-navy hover:text-white">
              Full history
            </Link>
          </div>
        </section>

        <section className="rounded-lg border border-border bg-white px-5 py-5 shadow-sm">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-navy">Access</h2>
          {user.role === "contractor" && user.contractor && (
            <dl className="mb-4 grid gap-2 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-steel">Verification</dt>
                <dd>{label(user.contractor.verification_status)}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-steel">Paid until</dt>
                <dd>{user.contractor.paid_until ? formatDateTime(user.contractor.paid_until, "en") : "not paid"}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-steel">Trial until</dt>
                <dd>{user.contractor.trial_until ? formatDateTime(user.contractor.trial_until, "en") : "none"}</dd>
              </div>
              {user.contractor.payment_override_active && (
                <div className="flex justify-between gap-4">
                  <dt className="text-steel">Admin override</dt>
                  <dd>active</dd>
                </div>
              )}
            </dl>
          )}
          {user.role === "owner" && user.owner && (
            <dl className="mb-4 grid gap-2 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-steel">Verification</dt>
                <dd>{label(user.owner.verification_status)}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-steel">Projects</dt>
                <dd>{user.owner.project_count}</dd>
              </div>
            </dl>
          )}
          {user.role === "admin" && <p className="mb-4 text-sm text-steel">Admin accounts have no marketplace access settings.</p>}

          {canSuspend ? (
            <button
              type="button"
              onClick={confirmToggle}
              disabled={suspend.isPending}
              className={`w-full rounded px-4 py-2.5 text-sm font-semibold disabled:opacity-60 ${user.is_suspended ? "bg-green-tint text-green" : "bg-red-tint text-red"}`}
            >
              {user.is_suspended ? "Reactivate account" : "Suspend account"}
            </button>
          ) : (
            <p className="text-[12px] text-steel-light">{isSelf ? "You cannot suspend your own account." : "Admin accounts cannot be suspended here."}</p>
          )}
        </section>
      </div>

      <section className="mt-5 rounded-lg border border-border bg-white px-5 py-5 shadow-sm">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-navy">Recent activity</h2>
        {!user.recent_activity.length ? (
          <p className="text-sm text-steel">Nothing recorded for this account yet.</p>
        ) : (
          <ul className="grid gap-2">
            {user.recent_activity.map((entry, index) => (
              <li key={`${entry.created_at}-${index}`} className="border-b border-border pb-2 text-[12.5px] last:border-0">
                <div className="font-mono text-[10px] text-steel-light">{entry.created_at ? formatDateTime(entry.created_at, "en") : ""}</div>
                <div>
                  <span className="font-semibold text-navy">{entry.action}</span>
                  {entry.previous_value !== null && entry.new_value !== null && (
                    <span className="text-steel-light">
                      {" "}
                      ({entry.previous_value} → {entry.new_value})
                    </span>
                  )}
                </div>
                {entry.reason && <div className="italic text-steel-light">"{entry.reason}"</div>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
