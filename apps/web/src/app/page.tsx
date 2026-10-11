import Link from "next/link";

const STEPS = [
  {
    title: "Register a public repository",
    body: "Only public, organization-owned GitHub repositories with a recognized open-source license are accepted.",
  },
  {
    title: "Import issues and optional CSV feedback",
    body: "Existing GitHub issues are combined with feedback you upload for the same product.",
  },
  {
    title: "Review evidence-backed themes",
    body: "Each theme links to an existing canonical issue. New issue drafts are created only with your confirmation.",
  },
];

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-10 px-6 py-16">
      <div className="flex flex-col gap-4">
        <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">
          Open-source product intelligence
        </p>
        <h1 className="text-4xl font-semibold tracking-tight">Feedback Intelligence Hub</h1>
        <p className="text-lg text-zinc-600 dark:text-zinc-400">
          Turn your project&apos;s GitHub issues and customer feedback into product themes, each linked
          to the issue that already tracks it.
        </p>
      </div>
      <ol className="grid gap-4 sm:grid-cols-3">
        {STEPS.map((step, index) => (
          <li key={step.title} className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <p className="text-sm font-semibold text-indigo-600">Step {index + 1}</p>
            <p className="mt-1 font-medium">{step.title}</p>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{step.body}</p>
          </li>
        ))}
      </ol>
      <div>
        <Link
          href="/dashboard"
          className="inline-flex rounded-md bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500"
        >
          Get started
        </Link>
      </div>
    </main>
  );
}
