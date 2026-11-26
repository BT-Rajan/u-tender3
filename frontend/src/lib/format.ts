// Display helpers shared by every page. Dates are always rendered in the
// language the user picked in the UI (not the browser's locale), so an
// Arabic-speaking user sees Arabic labels next to dates in the same
// format, and an English user never gets a surprise MM/DD/YYYY string.
// Latin digits are kept in both languages: tender deadlines are read
// alongside amounts and reference numbers, and mixing numeral systems on
// the same card reads badly.
//
// Time rule: the application's time is Kuwait time, everywhere. The server
// stores and sends times in UTC. Some values arrive without a zone marker;
// those are UTC too. Every value is shown in Asia/Kuwait, whatever the
// browser's own zone is. Kuwait is UTC+3 all year (no daylight saving), so
// conversions use that fixed offset.

export type DisplayLanguage = "en" | "ar";

export const KUWAIT_TIME_ZONE = "Asia/Kuwait";
const KUWAIT_OFFSET_HOURS = 3;

function localeTag(language: DisplayLanguage): string {
  return language === "ar" ? "ar-u-nu-latn" : "en-GB";
}

/** A server time as a Date. A value with no zone marker is UTC; a date-only value is a Kuwait day. */
export function parseIso(value: string): Date {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return new Date(`${value}T00:00:00+03:00`);
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(value);
  return new Date(hasZone ? value : `${value}Z`);
}

/** "30 Nov 2026" */
export function formatDate(iso: string, language: DisplayLanguage): string {
  return parseIso(iso).toLocaleDateString(localeTag(language), {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: KUWAIT_TIME_ZONE,
  });
}

/** "30 Nov 2026, 5:31 PM" */
export function formatDateTime(iso: string, language: DisplayLanguage): string {
  return parseIso(iso).toLocaleString(localeTag(language), {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: KUWAIT_TIME_ZONE,
  });
}

/** Compact form for cards where the year is noise: "30 Nov, 5:31 PM" */
export function formatDeadline(iso: string, language: DisplayLanguage): string {
  return parseIso(iso).toLocaleString(localeTag(language), {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZone: KUWAIT_TIME_ZONE,
  });
}

/** "11d 23h remaining" / "متبقي 11 يوم و 23 ساعة" */
export function timeRemaining(deadlineIso: string, language: DisplayLanguage = "en"): string {
  const diffMs = parseIso(deadlineIso).getTime() - Date.now();
  if (diffMs <= 0) return language === "ar" ? "انتهى الموعد" : "Deadline passed";
  const days = Math.floor(diffMs / 86_400_000);
  const hours = Math.floor((diffMs % 86_400_000) / 3_600_000);
  if (language === "ar") return `متبقي ${days} يوم و ${hours} ساعة`;
  return `${days}d ${hours}h remaining`;
}

/**
 * A datetime-local value typed in Kuwait ("2026-12-01T14:00") as the UTC ISO string the server expects.
 */
export function kuwaitInputToIso(value: string): string {
  const withSeconds = value.length === 16 ? `${value}:00` : value;
  return new Date(`${withSeconds}+0${KUWAIT_OFFSET_HOURS}:00`).toISOString();
}

/** A server time as a datetime-local value in Kuwait time ("2026-12-01T14:00"), for editing. */
export function isoToKuwaitInput(iso: string): string {
  const shifted = new Date(parseIso(iso).getTime() + KUWAIT_OFFSET_HOURS * 3_600_000);
  return shifted.toISOString().slice(0, 16);
}

/** The Kuwait calendar day, as YYYY-MM-DD, that is `daysAgo` days before today in Kuwait. */
export function kuwaitDay(daysAgo = 0): string {
  const shifted = new Date(Date.now() + KUWAIT_OFFSET_HOURS * 3_600_000 - daysAgo * 86_400_000);
  return shifted.toISOString().slice(0, 10);
}

export function stars(rating: number): string {
  const full = Math.round(rating ?? 0);
  return "★".repeat(full) + "☆".repeat(5 - full);
}
