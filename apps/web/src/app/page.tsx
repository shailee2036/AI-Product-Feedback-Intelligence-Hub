import Link from "next/link";
import { ArrowRight, FileSearch, Layers3, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";

const STEPS = [
  {
    title: "Register a public repository",
    body: "Only public, organization-owned GitHub repositories with a recognized open-source license are accepted.",
    icon: ShieldCheck,
    tint: "bg-teal-soft",
    iconColor: "text-accent",
  },
  {
    title: "Import issues and optional CSV feedback",
    body: "Existing GitHub issues are combined with feedback you upload for the same product.",
    icon: FileSearch,
    tint: "bg-coral-soft",
    iconColor: "text-coral",
  },
  {
    title: "Review evidence-backed themes",
    body: "Each theme links to an existing canonical issue. New issue drafts stay in the workspace.",
    icon: Layers3,
    tint: "bg-violet-soft",
    iconColor: "text-violet-600 dark:text-violet-300",
  },
];

const FEATURES = [
  {
    title: "Duplicates without extra issues",
    body: "Exact hashes and mutual nearest neighbors group the same request. Every original row is kept.",
    tint: "bg-gold-soft",
  },
  {
    title: "Human-approved themes",
    body: "Rename, merge, split, approve, or dismiss. Approved themes survive the next analysis run.",
    tint: "bg-teal-soft",
  },
  {
    title: "GitHub writes stay off",
    body: "Suggested comments, labels, and new-issue drafts are saved locally. Nothing is posted to GitHub.",
    tint: "bg-coral-soft",
  },
];

export default function Home() {
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <p className="font-semibold tracking-tight text-accent">Feedback Intelligence Hub</p>
        <Button asChild variant="ghost">
          <Link href="/login">Sign in</Link>
        </Button>
      </header>

      <main className="mx-auto flex max-w-6xl flex-col gap-20 px-6 pb-24">
        <section className="grid items-center gap-12 pt-10 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="flex flex-col gap-6">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-coral">
              Open-source product intelligence
            </p>
            <h1 className="text-5xl font-semibold tracking-tight text-balance">
              Turn public issues into themes you can act on.
            </h1>
            <p className="max-w-xl text-lg text-muted">
              Import a public GitHub repository, add an optional CSV, and review evidence-linked
              themes. Each theme points at an existing issue, or a local draft when none fits.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button asChild size="lg">
                <Link href="/dashboard">
                  Open workspace <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="secondary">
                <Link href="/login">Create an account</Link>
              </Button>
            </div>
          </div>
          <Card className="border-teal-200 bg-gradient-to-br from-teal-soft via-card to-coral-soft dark:border-teal-800">
            <p className="text-xs font-semibold uppercase tracking-wide text-accent">Pipeline</p>
            <ol className="mt-4 flex flex-col gap-3 text-sm">
              {[
                "Public GitHub issues",
                "Optional product CSV",
                "Normalized, redacted rows",
                "Embeddings and duplicates",
                "Themes, briefs, local drafts",
              ].map((step, index) => (
                <li key={step} className="flex items-center gap-3">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
                    {index + 1}
                  </span>
                  {step}
                </li>
              ))}
            </ol>
          </Card>
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          {STEPS.map((step, index) => {
            const Icon = step.icon;
            return (
              <Card key={step.title} className={step.tint}>
                <Icon className={`h-5 w-5 ${step.iconColor}`} />
                <p className={`mt-4 text-xs font-semibold uppercase tracking-wide ${step.iconColor}`}>
                  Step {index + 1}
                </p>
                <CardTitle className="mt-1">{step.title}</CardTitle>
                <CardDescription>{step.body}</CardDescription>
              </Card>
            );
          })}
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          {FEATURES.map((feature) => (
            <Card key={feature.title} className={feature.tint}>
              <CardTitle>{feature.title}</CardTitle>
              <CardDescription>{feature.body}</CardDescription>
            </Card>
          ))}
        </section>
      </main>
    </div>
  );
}
