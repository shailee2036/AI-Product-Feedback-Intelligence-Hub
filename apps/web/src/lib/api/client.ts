import "server-only";
import type { z } from "zod";

import { getServerEnv } from "@/lib/server-env";

import { ApiError, parseErrorDetail } from "./errors";
import { meSchema, productSchema, type Me, type Product } from "./types";

const TIMEOUT_MS = 15_000;

type RequestOptions = {
  method?: "GET" | "POST";
  body?: unknown;
  accessToken: string;
};

async function request<S extends z.ZodType>(
  path: string,
  schema: S,
  { method = "GET", body, accessToken }: RequestOptions,
): Promise<z.infer<S>> {
  const { apiUrl } = getServerEnv();
  let response: Response;
  try {
    response = await fetch(new URL(path, apiUrl), {
      method,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    throw new ApiError(503, { message: "The API is unreachable.", reasons: [] });
  }

  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiError(response.status, parseErrorDetail(response.status, payload));
  return schema.parse(payload);
}

export function getMe(accessToken: string): Promise<Me> {
  return request("/v1/me", meSchema, { accessToken });
}

export async function getProduct(accessToken: string): Promise<Product | null> {
  try {
    return await request("/v1/product", productSchema, { accessToken });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function registerGithubProduct(accessToken: string, repository: string): Promise<Product> {
  return request("/v1/product/github", productSchema, {
    method: "POST",
    body: { repository },
    accessToken,
  });
}
