import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { signOut } from "@/app/login/actions";
import { getClusters, getCurrentEmbeddings, getCurrentImport, getDuplicates, getFeedback, getMe, getProduct } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { ClusterReport, DuplicateReport, EmbeddingStatus, FeedbackPage, ImportJob, Me, Product } from "@/lib/api/types";
import { getVerifiedAccessToken } from "@/lib/supabase/server";

import { ClusterPanel } from "./cluster-panel";
import { CsvPanel } from "./csv-panel";
import { DuplicatePanel } from "./duplicate-panel";
import { EmbeddingPanel } from "./embedding-panel";
import { ImportPanel } from "./import-panel";
import { RegisterRepositoryForm } from "./register-form";

export const metadata: Metadata = { title: "Dashboard · Feedback Intelligence Hub" };

type Loaded =
  | {
      me: Me;
      product: Product | null;
      job: ImportJob | null;
      feedback: FeedbackPage;
      csvFeedback: FeedbackPage;
      embeddings: EmbeddingStatus | null;
      duplicates: DuplicateReport | null;
      clusters: ClusterReport | null;
    }
  | { error: string };

const EMPTY_FEEDBACK: FeedbackPage = { total: 0, items: [] };

async function load(token: string): Promise<Loaded> {
  try {
    const me = await getMe(token);
    const product = await getProduct(token);
    if (!product) {
      return {
        me,
        product,
        job: null,
        feedback: EMPTY_FEEDBACK,
        csvFeedback: EMPTY_FEEDBACK,
        embeddings: null,
        duplicates: null,
        clusters: null,
      };
    }
    const [job, feedback, csvFeedback, embeddings, duplicates, clusters] = await Promise.all([
      getCurrentImport(token),
      getFeedback(token, { source: "github_issue", limit: 20 }),
      getFeedback(token, { source: "csv", limit: 50 }),
      getCurrentEmbeddings(token),
      getDuplicates(token),
      getClusters(token),
    ]);
    return { me, product, job, feedback, csvFeedback, embeddings, duplicates, clusters };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login?next=/dashboard");
    return { error: error instanceof ApiError ? error.detail.message : "Something went wrong." };
  }
}

export default async function DashboardPage() {
  const token = await getVerifiedAccessToken();
  if (!token) redirect("/login?next=/dashboard");

  const data = await load(token);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-6 py-12">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          {"me" in data ? (
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              {data.me.workspace.name} · {data.me.email}
            </p>
          ) : null}
        </div>
        <form action={signOut}>
          <button type="submit" className="text-sm text-zinc-600 hover:underline dark:text-zinc-400">
            Sign out
          </button>
        </form>
      </header>

      {"error" in data ? (
        <section role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <p className="font-medium">Could not load your workspace.</p>
          <p className="mt-1">{data.error}</p>
        </section>
      ) : data.product ? (
        <ProductCard
          product={data.product}
          job={data.job}
          feedback={data.feedback}
          csvFeedback={data.csvFeedback}
          embeddings={data.embeddings}
          duplicates={data.duplicates}
          clusters={data.clusters}
        />
      ) : (
        <section className="rounded-lg border border-zinc-200 p-6 dark:border-zinc-800">
          <h2 className="text-lg font-semibold">Register your product</h2>
          <p className="mt-1 mb-4 text-sm text-zinc-600 dark:text-zinc-400">
            Each workspace tracks one open-source product through its public GitHub repository.
          </p>
          <RegisterRepositoryForm />
        </section>
      )}
    </main>
  );
}

function ProductCard({
  product,
  job,
  feedback,
  csvFeedback,
  embeddings,
  duplicates,
  clusters,
}: {
  product: Product;
  job: ImportJob | null;
  feedback: FeedbackPage;
  csvFeedback: FeedbackPage;
  embeddings: EmbeddingStatus | null;
  duplicates: DuplicateReport | null;
  clusters: ClusterReport | null;
}) {
  const repo = product.repository;
  const registered = new Date(product.created_at).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <section className="flex flex-col gap-6">
      <div className="rounded-lg border border-zinc-200 p-6 dark:border-zinc-800">
        <p className="text-sm font-semibold text-indigo-600">Registered product</p>
        <h2 className="mt-1 text-xl font-semibold">{product.name}</h2>
        <a
          href={repo.html_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-indigo-600 hover:underline"
        >
          {repo.full_name}
        </a>
        <dl className="mt-4 grid grid-cols-3 gap-4 text-sm">
          <div>
            <dt className="text-zinc-500">License</dt>
            <dd className="font-medium">{repo.license_spdx}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Default branch</dt>
            <dd className="font-medium">{repo.default_branch}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Registered</dt>
            <dd className="font-medium">{registered}</dd>
          </div>
        </dl>
      </div>
      <ImportPanel job={job} feedback={feedback} />
      <CsvPanel feedback={csvFeedback} />
      {embeddings ? <EmbeddingPanel status={embeddings} /> : null}
      {duplicates ? <DuplicatePanel report={duplicates} /> : null}
      {clusters ? <ClusterPanel report={clusters} /> : null}
    </section>
  );
}
