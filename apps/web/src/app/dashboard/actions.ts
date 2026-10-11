"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { registerGithubProduct } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { describeReason } from "@/lib/eligibility";
import { parseRepositoryInput } from "@/lib/repository";
import { getVerifiedAccessToken } from "@/lib/supabase/server";

export type RegisterState = {
  error?: string;
  reasons?: string[];
  repository?: string;
};

export async function registerRepository(
  _previous: RegisterState,
  formData: FormData,
): Promise<RegisterState> {
  const raw = formData.get("repository");
  const parsed = parseRepositoryInput(raw);
  const repository = typeof raw === "string" ? raw : undefined;
  if (!parsed.ok) return { error: parsed.error, repository };

  const token = await getVerifiedAccessToken();
  if (!token) redirect("/login?next=/dashboard");

  try {
    await registerGithubProduct(token, parsed.value);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return { ...describeRegistrationError(error), repository };
  }

  revalidatePath("/dashboard");
  redirect("/dashboard");
}

function describeRegistrationError(error: ApiError): RegisterState {
  switch (error.status) {
    case 404:
      return { error: "No public GitHub repository exists at that address." };
    case 409:
      return { error: "This workspace already has a registered product." };
    case 422:
      return error.detail.reasons.length
        ? {
            error: "This repository can't be registered:",
            reasons: error.detail.reasons.map(describeReason),
          }
        : { error: error.detail.message };
    case 503:
      return { error: "GitHub or the API is temporarily unavailable. Try again in a minute." };
    default:
      return { error: error.detail.message };
  }
}
