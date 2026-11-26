// The trades a tender or a contractor can name. Must match TRADE_OPTIONS in
// backend/app/services/registration.py (a test checks this).
export const TRADE_OPTIONS = [
  "General contracting",
  "Electrical",
  "Plumbing",
  "HVAC",
  "Civil works",
  "Finishing",
  "Fire safety",
  "Landscaping",
  "Other",
] as const;

// Today as the start of the day in Kuwait time, for a datetime-local minimum (YYYY-MM-DDT00:00).
export function todayKuwaitStart(): string {
  const day = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kuwait",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  return `${day}T00:00`;
}
