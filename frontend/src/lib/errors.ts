import { ApiError } from "@/api/client";

// The message to show for a failed request. FastAPI validation errors carry a list, not a
// sentence, so only a plain-text detail is shown; anything else gets the fallback.
export function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback;
}
