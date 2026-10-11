export type ApiErrorDetail = {
  message: string;
  reasons: string[];
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: ApiErrorDetail,
  ) {
    super(detail.message);
    this.name = "ApiError";
  }
}

/** Normalize FastAPI error bodies: `{detail: string}`, `{detail: {message, reasons}}`, or validation lists. */
export function parseErrorDetail(status: number, body: unknown): ApiErrorDetail {
  const detail = isRecord(body) ? body.detail : undefined;

  if (typeof detail === "string") return { message: detail, reasons: [] };
  if (isRecord(detail)) {
    const reasons = Array.isArray(detail.reasons)
      ? detail.reasons.filter((r): r is string => typeof r === "string")
      : [];
    const message = typeof detail.message === "string" ? detail.message : fallback(status);
    return { message, reasons };
  }
  if (Array.isArray(detail) && isRecord(detail[0]) && typeof detail[0].msg === "string") {
    return { message: detail[0].msg, reasons: [] };
  }
  return { message: fallback(status), reasons: [] };
}

function fallback(status: number): string {
  return status >= 500 ? "The service is temporarily unavailable." : `Request failed (${status}).`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
