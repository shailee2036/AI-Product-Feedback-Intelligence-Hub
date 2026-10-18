"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardDescription, CardTitle } from "@/components/ui/card";

export function OverviewCharts({
  github,
  csv,
  themes,
}: {
  github: number;
  csv: number;
  themes: { name: string; score: number }[];
}) {
  const sources = [
    { name: "GitHub", count: github },
    { name: "CSV", count: csv },
  ];

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardTitle>Feedback by source</CardTitle>
        <CardDescription>Imported GitHub issues and uploaded CSV rows.</CardDescription>
        <div className="mt-4 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={sources} barSize={48}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tickLine={false} axisLine={false} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
              <Tooltip />
              <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                <Cell fill="var(--accent)" />
                <Cell fill="var(--coral)" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card>
        <CardTitle>Theme scores</CardTitle>
        <CardDescription>Deterministic scores from size, recency, sources, and completeness.</CardDescription>
        <div className="mt-4 h-64">
          {themes.length === 0 ? (
            <p className="text-sm text-muted">Find themes to see scores here.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={themes} layout="vertical" margin={{ left: 16 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="name" width={120} tickLine={false} axisLine={false} />
                <Tooltip />
                <Bar dataKey="score" fill="var(--coral)" radius={[0, 8, 8, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </Card>
    </div>
  );
}
