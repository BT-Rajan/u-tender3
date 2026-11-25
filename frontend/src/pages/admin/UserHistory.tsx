import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";

interface HistoryEntry {
  id: string;
  action: string;
  target_type: string;
  target_id: string;
  actor_id: string | null;
  actor_name: string;
  previous_value: string | null;
  new_value: string | null;
  reason: string | null;
  created_at: string;
}

function formatWhen(value: string, language: string): string {
  const date = new Date(value.endsWith("Z") ? value : `${value}Z`);
  return new Intl.DateTimeFormat(language === "ar" ? "ar" : "en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function changeText(entry: HistoryEntry): string | null {
  if (!entry.previous_value && !entry.new_value) return null;
  return [entry.previous_value ? `from ${entry.previous_value}` : "", entry.new_value ? `to ${entry.new_value}` : ""]
    .filter(Boolean)
    .join(" ");
}

export function AdminUserHistoryPage() {
  const { userId = "" } = useParams();
  const { t, language } = useI18n();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-user-history", userId],
    queryFn: () => apiFetch<HistoryEntry[]>(`/admin/users/${userId}/history`),
    enabled: Boolean(userId),
  });

  return (
    <section className="mx-auto max-w-4xl">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold text-navy">{t("history.title")}</h1>
        <Link to="/admin/owners" className="text-sm font-semibold text-navy hover:underline">
          {t("history.back")}
        </Link>
      </div>

      {isLoading && <p className="text-sm text-steel">…</p>}
      {isError && (
        <p role="alert" className="rounded border border-red bg-red-tint px-4 py-3 text-sm text-red">
          {t("history.loadError")}
        </p>
      )}

      {data && data.length === 0 && <p className="text-sm text-steel">{t("history.empty")}</p>}

      {data && data.length > 0 && (
        <ol className="divide-y divide-border rounded border border-border bg-white">
          {data.map((entry) => (
            <li key={entry.id} className="grid gap-2 px-5 py-4 sm:grid-cols-[1fr_auto]">
              <div>
                <div className="font-semibold text-ink">{entry.action}</div>
                <div className="mt-1 text-sm text-steel">
                  <span>{t("history.by")}: {entry.actor_id ? entry.actor_name : t("history.system")}</span>
                  {entry.reason && <span> · {t("history.reason")}: {entry.reason}</span>}
                </div>
                {changeText(entry) && (
                  <div className="mt-1 text-sm text-steel">
                    {t("history.changed")}: {changeText(entry)}
                  </div>
                )}
              </div>
              <time dateTime={entry.created_at} className="text-sm text-steel sm:text-right">
                {formatWhen(entry.created_at, language)}
              </time>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
