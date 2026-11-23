// Display helpers shared by every page. Dates are always rendered in the
// language the user picked in the UI (not the browser's locale), so an
// Arabic-speaking user sees Arabic labels next to dates in the same
// format, and an English user never gets a surprise MM/DD/YYYY string.
// Latin digits are kept in both languages: tender deadlines are read
// alongside amounts and reference numbers, and mixing numeral systems on
// the same card reads badly.

export type DisplayLanguage = "en" | "ar";

function localeTag(language: DisplayLanguage): string {
  return language === "ar" ? "ar-u-nu-latn" : "en-GB";
}

/** "30 Nov 2026" */
export function formatDate(iso: string, language: DisplayLanguage): string {
  return new Date(iso).toLocaleDateString(localeTag(language), {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** "30 Nov 2026, 5:31 PM" */
export function formatDateTime(iso: string, language: DisplayLanguage): string {
  return new Date(iso).toLocaleString(localeTag(language), {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Compact form for cards where the year is noise: "30 Nov, 5:31 PM" */
export function formatDeadline(iso: string, language: DisplayLanguage): string {
  return new Date(iso).toLocaleString(localeTag(language), {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** "11d 23h remaining" / "متبقي 11 يوم و 23 ساعة" */
export function timeRemaining(deadlineIso: string, language: DisplayLanguage = "en"): string {
  const diffMs = new Date(deadlineIso).getTime() - Date.now();
  if (diffMs <= 0) return language === "ar" ? "انتهى الموعد" : "Deadline passed";
  const days = Math.floor(diffMs / 86_400_000);
  const hours = Math.floor((diffMs % 86_400_000) / 3_600_000);
  if (language === "ar") return `متبقي ${days} يوم و ${hours} ساعة`;
  return `${days}d ${hours}h remaining`;
}

export function stars(rating: number): string {
  const full = Math.round(rating ?? 0);
  return "★".repeat(full) + "☆".repeat(5 - full);
}
