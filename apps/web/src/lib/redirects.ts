const DEFAULT_PATH = "/dashboard";

/** Only allow same-site relative paths, so `?next=` cannot become an open redirect. */
export function safeNextPath(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return DEFAULT_PATH;
  }
  try {
    const url = new URL(value, "http://localhost");
    if (url.origin !== "http://localhost") return DEFAULT_PATH;
    return url.pathname + url.search;
  } catch {
    return DEFAULT_PATH;
  }
}
