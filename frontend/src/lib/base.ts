// The path the app is served under without its trailing slash, for example /utender. Empty at the root.
export const APP_BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

// An app path with the base added, for links written as plain <a href> tags.
export function withBase(path: string): string {
  return `${APP_BASE}${path}`;
}
