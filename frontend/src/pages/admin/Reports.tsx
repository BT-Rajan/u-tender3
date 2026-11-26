import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { ActivationReport, BillingReport, SummaryReport, TenderReport } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { PageLoading } from "@/components/PageLoading";
import { QueryError } from "@/components/QueryError";
import { errorText } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";

const INPUT =
  "rounded border border-border bg-white px-3 py-2 text-sm text-ink focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20";

// Dates in the browser's own calendar, as YYYY-MM-DD.
function localDate(daysAgo = 0): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return d.toLocaleDateString("en-CA");
}

function label(value: string) {
  return value.replace(/_/g, " ");
}

function Header({ eyebrow, title, intro }: { eyebrow: string; title: string; intro: string }) {
  return (
    <div className="mb-6">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-widest text-amber-dark">{eyebrow}</span>
      <h1 className="mb-1 font-display text-3xl font-bold text-navy">{title}</h1>
      <p className="text-[13.5px] text-steel">{intro}</p>
    </div>
  );
}

function Card({ title, value, hint }: { title: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border border-border bg-white px-4 py-4 shadow-sm">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-steel">{title}</div>
      <div className="mt-1 font-display text-2xl font-bold text-navy">{value}</div>
      {hint && <div className="mt-1 text-[11.5px] text-steel-light">{hint}</div>}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-6">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-navy">{title}</h2>
      {children}
    </section>
  );
}

function Breakdown({ values }: { values: Record<string, number> }) {
  const entries = Object.entries(values);
  if (!entries.length) return <p className="text-sm text-steel">None yet.</p>;
  return (
    <ul className="grid gap-2 text-sm">
      {entries.map(([key, count]) => (
        <li key={key} className="flex justify-between gap-4 border-b border-border pb-2 last:border-0">
          <span className="text-steel">{label(key)}</span>
          <span className="font-mono font-semibold text-navy">{count}</span>
        </li>
      ))}
    </ul>
  );
}

// Downloads a report's full period as a CSV file. The API returns the file; the browser saves it.
async function downloadCsv(path: string, filename: string) {
  const blob = await apiFetch<Blob>(path);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function PeriodControls({
  from,
  to,
  onChange,
  csvPath,
  csvName,
}: {
  from: string;
  to: string;
  onChange: (next: { from: string; to: string }) => void;
  csvPath: string;
  csvName: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="mb-6">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-steel">From</label>
          <input type="date" value={from} max={to} onChange={(e) => onChange({ from: e.target.value, to })} className={INPUT} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-steel">To</label>
          <input type="date" value={to} min={from} onChange={(e) => onChange({ from, to: e.target.value })} className={INPUT} />
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => onChange({ from: localDate(6), to: localDate() })} className="rounded border border-navy px-3 py-2 text-xs font-semibold text-navy">
            Last 7 days
          </button>
          <button type="button" onClick={() => onChange({ from: localDate(29), to: localDate() })} className="rounded border border-navy px-3 py-2 text-xs font-semibold text-navy">
            Last 30 days
          </button>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await downloadCsv(`${csvPath}${csvPath.includes("?") ? "&" : "?"}format=csv`, csvName);
            } catch (err) {
              setError(errorText(err, "Could not download the file."));
            } finally {
              setBusy(false);
            }
          }}
          className="ml-auto rounded bg-navy px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          {busy ? "Preparing..." : "Download CSV"}
        </button>
      </div>
      {error && <p className="mt-3 text-sm text-red">{error}</p>}
    </div>
  );
}

function periodQuery(from: string, to: string) {
  return `from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
}

function ReportError({ error, retry }: { error: unknown; retry: () => void }) {
  if (error instanceof ApiError && error.status === 400) {
    return <ErrorBanner message={errorText(error, "Check the dates.")} />;
  }
  return <QueryError onRetry={retry} />;
}

export function AdminReportsOverviewPage() {
  const { data, isError, error, refetch } = useQuery({
    queryKey: ["admin-report-summary"],
    queryFn: () => apiFetch<SummaryReport>("/admin/reports/summary"),
  });
  if (isError) return <ReportError error={error} retry={() => refetch()} />;
  if (!data) return <PageLoading />;

  return (
    <div className="mx-auto max-w-6xl">
      <Header
        eyebrow="Admin · Reports"
        title="Overview"
        intro={`Platform totals as they stood at ${formatDateTime(data.generated_at, "en")} UTC.`}
      />

      <Section title="People">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card title="Owners" value={data.users.owner ?? 0} />
          <Card title="Contractors" value={data.users.contractor ?? 0} />
          <Card title="Admins" value={data.users.admin ?? 0} />
          <Card title="Active contractors" value={data.contractors.active} hint="Can send offers now" />
        </div>
      </Section>

      <Section title="Contractor billing">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card title="Paid now" value={data.contractors.paid} />
          <Card title="On trial" value={data.contractors.on_trial} />
          <Card title="Waiting for activation" value={data.contractors.waiting_activation} />
          <Card
            title="Activation overdue"
            value={data.contractors.activation_overdue}
            hint="Past the 48-hour target"
          />
        </div>
      </Section>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-lg border border-border bg-white px-5 py-5 shadow-sm">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-navy">Contractors by status</h2>
          <Breakdown values={data.contractors.by_status} />
        </div>
        <div className="rounded-lg border border-border bg-white px-5 py-5 shadow-sm">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-navy">Owners by status</h2>
          <Breakdown values={data.owners.by_status} />
        </div>
        <div className="rounded-lg border border-border bg-white px-5 py-5 shadow-sm">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-navy">Tenders ({data.projects.total})</h2>
          <Breakdown values={data.projects.by_status} />
        </div>
        <div className="rounded-lg border border-border bg-white px-5 py-5 shadow-sm">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-navy">Offers ({data.offers.total})</h2>
          <Breakdown values={data.offers.by_status} />
          <p className="mt-4 text-sm text-steel">
            Awarded: <span className="font-mono font-semibold text-navy">{data.awards.count}</span> worth{" "}
            <span className="font-mono font-semibold text-navy">{data.awards.value}</span>
          </p>
        </div>
      </div>
    </div>
  );
}

export function AdminTenderReportPage() {
  const [range, setRange] = useState({ from: localDate(29), to: localDate() });
  const { data, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["admin-report-tenders", range.from, range.to],
    queryFn: () => apiFetch<TenderReport>(`/admin/reports/tenders?${periodQuery(range.from, range.to)}`),
  });

  return (
    <div className="mx-auto max-w-6xl">
      <Header eyebrow="Admin · Reports" title="Tenders" intro="Tenders published in the period, the offers they drew, and what was awarded." />
      <PeriodControls
        from={range.from}
        to={range.to}
        onChange={setRange}
        csvPath={`/admin/reports/tenders?${periodQuery(range.from, range.to)}`}
        csvName={`tenders-${range.from}-${range.to}.csv`}
      />
      {isError ? (
        <ReportError error={error} retry={() => refetch()} />
      ) : !data ? (
        <PageLoading />
      ) : (
        <div className={isFetching ? "opacity-60" : ""}>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card title="Tenders published" value={data.summary.projects_created} />
            <Card title="Offers received" value={data.summary.offers_received} />
            <Card title="Awards" value={data.summary.awards} />
            <Card title="Awarded value" value={data.summary.awarded_value} />
          </div>
          <Section title="Tenders by status">
            <div className="rounded-lg border border-border bg-white px-5 py-4 shadow-sm">
              <Breakdown values={data.summary.by_status} />
            </div>
          </Section>
          <Section title="Tenders">
            <ReportTable
              empty="No tenders were published in this period."
              rows={data.rows}
              total={data.rows_total}
              columns={[
                { key: "reference", title: "Ref" },
                { key: "title", title: "Title" },
                { key: "owner", title: "Owner" },
                { key: "status", title: "Status", format: label },
                { key: "offers", title: "Offers" },
                { key: "awarded_amount", title: "Awarded" },
                { key: "created_at", title: "Published", format: (v) => (v ? formatDateTime(v, "en") : "") },
              ]}
            />
          </Section>
        </div>
      )}
    </div>
  );
}

export function AdminBillingReportPage() {
  const [range, setRange] = useState({ from: localDate(29), to: localDate() });
  const { data, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["admin-report-billing", range.from, range.to],
    queryFn: () => apiFetch<BillingReport>(`/admin/reports/billing?${periodQuery(range.from, range.to)}`),
  });

  return (
    <div className="mx-auto max-w-6xl">
      <Header eyebrow="Admin · Reports" title="Billing" intro="Invoices paid in the period. Totals are kept separately for each currency." />
      <PeriodControls
        from={range.from}
        to={range.to}
        onChange={setRange}
        csvPath={`/admin/reports/billing?${periodQuery(range.from, range.to)}`}
        csvName={`billing-${range.from}-${range.to}.csv`}
      />
      {isError ? (
        <ReportError error={error} retry={() => refetch()} />
      ) : !data ? (
        <PageLoading />
      ) : (
        <div className={isFetching ? "opacity-60" : ""}>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card title="Invoices paid" value={data.summary.paid_count} hint={`${data.summary.by_kind.activation} first payments, ${data.summary.by_kind.monthly} monthly`} />
            <Card
              title="Collected"
              value={Object.keys(data.summary.totals).length ? Object.entries(data.summary.totals).map(([c, v]) => `${v} ${c}`).join(" · ") : "0"}
            />
            <Card title="Still pending" value={data.summary.still_pending} hint={`${data.summary.invoices_created} created in the period`} />
            <Card title="Canceled or expired" value={data.summary.canceled_or_expired} />
          </div>
          <div className="mb-6 grid gap-5 lg:grid-cols-2">
            <div className="rounded-lg border border-border bg-white px-5 py-5 shadow-sm">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-navy">By plan</h2>
              {!data.summary.by_plan.length ? (
                <p className="text-sm text-steel">No payments in this period.</p>
              ) : (
                <ul className="grid gap-2 text-sm">
                  {data.summary.by_plan.map((plan) => (
                    <li key={plan.plan} className="flex justify-between gap-4 border-b border-border pb-2 last:border-0">
                      <span className="text-steel">
                        {plan.plan} <span className="font-mono text-steel-light">×{plan.count}</span>
                      </span>
                      <span className="font-mono font-semibold text-navy">
                        {Object.entries(plan.totals).map(([c, v]) => `${v} ${c}`).join(" · ")}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-lg border border-border bg-white px-5 py-5 shadow-sm">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-navy">Right now</h2>
              <dl className="grid gap-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-steel">Contractors paid</dt>
                  <dd className="font-mono font-semibold">{data.summary.paid_contractors_now}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-steel">Contractors on trial</dt>
                  <dd className="font-mono font-semibold">{data.summary.trials_now}</dd>
                </div>
              </dl>
            </div>
          </div>
          <Section title="Paid invoices">
            <ReportTable
              empty="No invoices were paid in this period."
              rows={data.rows}
              total={data.rows_total}
              columns={[
                { key: "paid_at", title: "Paid", format: (v) => (v ? formatDateTime(v, "en") : "") },
                { key: "company", title: "Company" },
                { key: "plan", title: "Plan" },
                { key: "kind", title: "Kind", format: label },
                { key: "amount", title: "Amount", format: (v, row) => `${v} ${row.currency}` },
                { key: "reference", title: "Reference" },
              ]}
            />
          </Section>
        </div>
      )}
    </div>
  );
}

export function AdminActivationReportPage() {
  const [range, setRange] = useState({ from: localDate(29), to: localDate() });
  const { data, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["admin-report-activations", range.from, range.to],
    queryFn: () => apiFetch<ActivationReport>(`/admin/reports/activations?${periodQuery(range.from, range.to)}`),
  });

  return (
    <div className="mx-auto max-w-6xl">
      <Header
        eyebrow="Admin · Reports"
        title="Activations"
        intro="Contractors whose first payment was made in the period, and how long the admin took to activate them."
      />
      <PeriodControls
        from={range.from}
        to={range.to}
        onChange={setRange}
        csvPath={`/admin/reports/activations?${periodQuery(range.from, range.to)}`}
        csvName={`activations-${range.from}-${range.to}.csv`}
      />
      {isError ? (
        <ReportError error={error} retry={() => refetch()} />
      ) : !data ? (
        <PageLoading />
      ) : (
        <div className={isFetching ? "opacity-60" : ""}>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card title="First payments" value={data.summary.first_payments} />
            <Card
              title="Within 48 hours"
              value={data.summary.activated_within_sla}
              hint={`Target ${data.summary.activation_target_hours} hours`}
            />
            <Card title="Activated late" value={data.summary.activated_late} />
            <Card
              title="Average to activate"
              value={data.summary.average_hours_to_activate === null ? "-" : `${data.summary.average_hours_to_activate} h`}
            />
          </div>
          <p className="mb-6 text-sm text-steel">
            Queue right now: <span className="font-mono font-semibold text-navy">{data.summary.queue_now}</span> waiting,{" "}
            <span className="font-mono font-semibold text-red">{data.summary.queue_overdue_now}</span> overdue.{" "}
            <Link to="/admin/activations" className="font-semibold text-navy underline">
              Open the activation queue
            </Link>
          </p>
          <Section title="Contractors">
            <ReportTable
              empty="No first payments were made in this period."
              rows={data.rows}
              total={data.rows_total}
              columns={[
                { key: "company", title: "Company" },
                { key: "contact", title: "Contact" },
                { key: "paid_at", title: "Paid", format: (v) => (v ? formatDateTime(v, "en") : "") },
                { key: "activated_at", title: "Activated", format: (v) => (v ? formatDateTime(v, "en") : "not yet") },
                { key: "hours_to_activate", title: "Hours", format: (v) => (v === "" || v === null ? "" : String(v)) },
                { key: "status", title: "Status", format: label },
              ]}
            />
          </Section>
        </div>
      )}
    </div>
  );
}

interface Column<T> {
  key: keyof T & string;
  title: string;
  format?: (value: any, row: T) => string;
}

// The first rows of a report. The CSV button above has every row in the period.
function ReportTable<T extends object>({
  rows,
  total,
  columns,
  empty,
}: {
  rows: T[];
  total: number;
  columns: Column<T>[];
  empty: string;
}) {
  if (!rows.length) {
    return <div className="rounded-lg border border-dashed border-border bg-white p-8 text-center text-sm text-steel">{empty}</div>;
  }
  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-border bg-white shadow-sm">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key} className="border-b border-border px-2.5 py-2 text-left text-xs font-semibold uppercase tracking-wide text-steel">
                  {column.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-b border-border">
                {columns.map((column) => {
                  const value = (row as Record<string, unknown>)[column.key];
                  const text = column.format ? column.format(value, row) : value === null || value === undefined ? "" : String(value);
                  return (
                    <td key={column.key} className="px-2.5 py-2.5 text-[12.5px]">
                      {text}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {total > rows.length && (
        <p className="mt-3 text-sm text-steel">
          Showing the first {rows.length} of {total}. Download the CSV for all of them.
        </p>
      )}
    </>
  );
}
