import { useI18n } from "@/i18n/I18nContext";

// The word that starts U-Tender on WhatsApp. The shared number forwards
// messages containing it to U-Tender; anything else gets a short hint.
export const WHATSAPP_TRIGGER = "utender";

/** A wa.me link that opens a chat with the number and fills in the trigger word. Null when no number is configured. */
export function whatsappLink(number: string | undefined): string | null {
  const digits = (number ?? "").replace(/\D/g, "");
  if (!digits) return null;
  return `https://wa.me/${digits}?text=${encodeURIComponent(WHATSAPP_TRIGGER)}`;
}

export function WhatsAppCard() {
  const { t } = useI18n();
  const href = whatsappLink(import.meta.env.VITE_WHATSAPP_NUMBER);
  if (!href) return null;

  return (
    <section className="bg-white border border-border rounded px-5 py-4 mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div>
        <h2 className="font-display text-base font-semibold text-navy mb-1">{t("whatsapp.title")}</h2>
        <p className="text-[13px] text-steel leading-relaxed">{t("whatsapp.body")}</p>
      </div>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="shrink-0 bg-green hover:opacity-90 text-white text-sm font-semibold rounded px-5 py-2.5 text-center"
      >
        {t("whatsapp.cta")}
      </a>
    </section>
  );
}
