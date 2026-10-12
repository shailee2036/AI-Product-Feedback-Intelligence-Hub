"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  cancelIssueImport,
  findClusters,
  findDuplicates,
  nameClusters,
  registerGithubProduct,
  startEmbeddings,
  startIssueImport,
  uploadFeedbackCsv,
} from "@/lib/api/client";
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

export type ImportState = { error?: string };

export type CsvUploadState = { error?: string; reasons?: string[]; saved?: number };

export async function uploadCsv(
  _previous: CsvUploadState,
  formData: FormData,
): Promise<CsvUploadState> {
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) return { error: "Choose a CSV file." };
  if (!file.name.toLowerCase().endsWith(".csv")) return { error: "Choose a .csv file." };

  const token = await getVerifiedAccessToken();
  if (!token) redirect("/login?next=/dashboard");
  try {
    const result = await uploadFeedbackCsv(token, file);
    revalidatePath("/dashboard");
    return { saved: result.imported_count };
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 404) return { error: "Register a repository before uploading feedback." };
    return { error: error.detail.message, reasons: error.detail.reasons };
  }
}

export type EmbeddingState = { error?: string };

export type DuplicateState = { error?: string };

export type ClusterState = { error?: string };

export async function nameThemes(): Promise<ClusterState> {
  const token = await getVerifiedAccessToken();
  if (!token) redirect("/login?next=/dashboard");
  try {
    await nameClusters(token);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 404) return { error: "Register a repository before naming themes." };
    return { error: error.detail.message };
  }
  revalidatePath("/dashboard");
  return {};
}

export async function findThemes(): Promise<ClusterState> {
  const token = await getVerifiedAccessToken();
  if (!token) redirect("/login?next=/dashboard");
  try {
    await findClusters(token);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 404) return { error: "Register a repository before finding themes." };
    return { error: error.detail.message };
  }
  revalidatePath("/dashboard");
  return {};
}

export async function findDuplicateFeedback(): Promise<DuplicateState> {
  const token = await getVerifiedAccessToken();
  if (!token) redirect("/login?next=/dashboard");
  try {
    await findDuplicates(token);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 404) return { error: "Register a repository before finding duplicates." };
    return { error: error.detail.message };
  }
  revalidatePath("/dashboard");
  return {};
}

export async function startEmbedding(): Promise<EmbeddingState> {
  const token = await getVerifiedAccessToken();
  if (!token) redirect("/login?next=/dashboard");
  try {
    await startEmbeddings(token);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 409) return { error: "An embedding run is already in progress." };
    if (error.status === 404) return { error: "Register a repository before embedding feedback." };
    return { error: error.detail.message };
  }
  revalidatePath("/dashboard");
  return {};
}

export async function startImport(): Promise<ImportState> {
  const token = await getVerifiedAccessToken();
  if (!token) redirect("/login?next=/dashboard");
  try {
    await startIssueImport(token);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 409) return { error: "An import is already running." };
    if (error.status === 404) return { error: "Register a repository before importing issues." };
    return { error: error.detail.message };
  }
  revalidatePath("/dashboard");
  return {};
}

export async function cancelImport(
  _previous: ImportState,
  formData: FormData,
): Promise<ImportState> {
  const importId = formData.get("importId");
  if (typeof importId !== "string" || importId.length === 0) return { error: "Missing import." };
  const token = await getVerifiedAccessToken();
  if (!token) redirect("/login?next=/dashboard");
  try {
    await cancelIssueImport(token, importId);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return { error: error.detail.message };
  }
  revalidatePath("/dashboard");
  return {};
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
