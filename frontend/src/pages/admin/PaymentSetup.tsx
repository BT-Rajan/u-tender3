import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { API_URL, apiFetch } from "@/api/client";
import type { BillingSettings, PlainSetting, SecretSetting } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { PageLoading } from "@/components/PageLoading";
import { QueryError } from "@/components/QueryError";
import { errorText } from "@/lib/errors";

const INPUT =
  "w-full rounded border border-border bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-steel/60 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/20";

const SOURCE_TEXT: Record<SecretSetting["source"], string> = {
  admin: "entered here",
  env: "from the server's .env file",
  none: "not set",
};

// A secret is never shown. The admin pastes a new value, or clears the one entered here.
function SecretField({
  label,
  help,
  setting,
  busy,
  onSave,
  onClear,
}: {
  label: string;
  help: string;
  setting: SecretSetting;
  busy: boolean;
  onSave: (value: string) => void;
  onClear: () => void;
}) {
  const [value, setValue] = useState("");
  const status = setting.configured ? `Saved ${setting.hint ?? ""} (${SOURCE_TEXT[setting.source]})` : "Not set";
  return (
    <div className="grid gap-2 border-b border-border pb-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <label className="text-xs font-semibold uppercase tracking-wide text-steel">{label}</label>
        <span className="font-mono text-[11px] text-steel-light">{status}</span>
      </div>
      <p className="text-[11.5px] text-steel-light">{help}</p>
      <div className="flex flex-wrap gap-2">
        <input
          type="password"
          autoComplete="off"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Paste the new value"
          className={`${INPUT} flex-1`}
        />
        <button
          type="button"
          disabled={busy || !value.trim()}
          onClick={() => {
            onSave(value.trim());
            setValue("");
          }}
          className="rounded bg-navy px-4 py-2 text-xs font-semibold text-white disabled:opacity-40"
        >
          Save
        </button>
        {setting.source === "admin" && (
          <button type="button" disabled={busy} onClick={onClear} className="rounded bg-red-tint px-4 py-2 text-xs font-semibold text-red disabled:opacity-40">
            Clear
          </button>
        )}
      </div>
    </div>
  );
}

// A plain value (the API address, the template name). Saved as typed; clearing restores the .env value.
function PlainField({
  label,
  help,
  setting,
  busy,
  onSave,
}: {
  label: string;
  help: string;
  setting: PlainSetting;
  busy: boolean;
  onSave: (value: string) => void;
}) {
  const [value, setValue] = useState(setting.value ?? "");
  return (
    <div className="grid gap-2 border-b border-border pb-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <label className="text-xs font-semibold uppercase tracking-wide text-steel">{label}</label>
        <span className="font-mono text-[11px] text-steel-light">{SOURCE_TEXT[setting.source]}</span>
      </div>
      <p className="text-[11.5px] text-steel-light">{help}</p>
      <div className="flex flex-wrap gap-2">
        <input value={value} onChange={(e) => setValue(e.target.value)} className={`${INPUT} flex-1`} />
        <button type="button" disabled={busy} onClick={() => onSave(value.trim())} className="rounded bg-navy px-4 py-2 text-xs font-semibold text-white disabled:opacity-40">
          Save
        </button>
        {setting.source === "admin" && (
          <button type="button" disabled={busy} onClick={() => onSave("")} className="rounded bg-red-tint px-4 py-2 text-xs font-semibold text-red disabled:opacity-40">
            Use .env value
          </button>
        )}
      </div>
    </div>
  );
}

export function AdminPaymentSetupPage() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { data, isError, refetch } = useQuery({
    queryKey: ["admin-billing-settings"],
    queryFn: () => apiFetch<BillingSettings>("/admin/settings/billing"),
  });

  const save = useMutation({
    mutationFn: (change: Partial<Record<"myfatoorah_api_key" | "myfatoorah_webhook_secret" | "myfatoorah_base_url" | "whatsapp_otp_template", string>>) =>
      apiFetch<BillingSettings>("/admin/settings/billing", { method: "PUT", body: change }),
    onSuccess: () => {
      setError(null);
      setNotice("Saved. Payments use this setting from now on.");
      queryClient.invalidateQueries({ queryKey: ["admin-billing-settings"] });
    },
    onError: (err) => {
      setNotice(null);
      setError(errorText(err, "Could not save this setting."));
    },
  });

  if (isError) return <QueryError onRetry={() => refetch()} />;
  if (!data) return <PageLoading />;

  const busy = save.isPending;
  const webhookUrl = `${API_URL}/billing/webhook/myfatoorah`;

  return (
    <main className="mx-auto max-w-3xl">
      <div className="mb-6">
        <span className="mb-1 block text-xs font-semibold uppercase tracking-widest text-amber-dark">Admin · Payment setup</span>
        <h1 className="mb-1 font-display text-3xl font-bold text-navy">Payment setup</h1>
        <p className="text-[13.5px] text-steel">
          Enter the MyFatoorah details here instead of on the server. A value saved here overrides the server's .env file. Secrets are stored encrypted and are never shown again.
        </p>
      </div>

      <div className="mb-6 rounded-lg border border-border bg-white px-5 py-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <span className={`rounded-full px-2.5 py-1 font-mono text-[10px] uppercase ${data.payments_ready ? "bg-green-tint text-green" : "bg-amber/15 text-amber-dark"}`}>
            {data.payments_ready ? "Payments ready" : "Payments not connected"}
          </span>
        </div>
        <p className="mt-3 text-[12px] text-steel">
          Webhook address to enter in MyFatoorah: <span className="font-mono break-all text-navy">{webhookUrl}</span>
        </p>
      </div>

      <ErrorBanner message={error} />
      {notice && !error && <p role="status" className="mb-4 rounded border border-blue bg-blue-tint px-3.5 py-2.5 text-sm text-blue">{notice}</p>}

      <div className="grid gap-5 rounded-lg border border-border bg-white px-5 py-5 shadow-sm">
        <SecretField
          label="MyFatoorah API token"
          help="From the MyFatoorah portal: Integration Settings, then API Key. Needed before any contractor can pay."
          setting={data.myfatoorah_api_key}
          busy={busy}
          onSave={(value) => save.mutate({ myfatoorah_api_key: value })}
          onClear={() => save.mutate({ myfatoorah_api_key: "" })}
        />
        <SecretField
          label="Webhook secret"
          help="The secret MyFatoorah signs webhooks with. Optional: without it, payments are still confirmed with MyFatoorah directly."
          setting={data.myfatoorah_webhook_secret}
          busy={busy}
          onSave={(value) => save.mutate({ myfatoorah_webhook_secret: value })}
          onClear={() => save.mutate({ myfatoorah_webhook_secret: "" })}
        />
        <PlainField
          label="API address"
          help="Use https://apitest.myfatoorah.com for testing and https://api.myfatoorah.com for live payments."
          setting={data.myfatoorah_base_url}
          busy={busy}
          onSave={(value) => save.mutate({ myfatoorah_base_url: value })}
        />
        <PlainField
          label="WhatsApp code template"
          help="The approved WhatsApp template that carries a sign-in code outside the 24-hour window. Leave empty to send plain text inside the window only."
          setting={data.whatsapp_otp_template}
          busy={busy}
          onSave={(value) => save.mutate({ whatsapp_otp_template: value })}
        />
      </div>
    </main>
  );
}
