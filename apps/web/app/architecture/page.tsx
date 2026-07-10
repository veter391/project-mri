import type { Metadata } from "next";
import { PageHeader } from "@/components/page-header";

export const metadata: Metadata = {
  title: "Architecture · project-mri",
  description: "A local-first pipeline: ingest and provenance normalization, analysis, explainable scoring, and human + agent interfaces.",
};

const LAYERS = [
  ["Ingest", "Pulls raw facts from heterogeneous sources — Git history, tree-sitter structure, optional AI-tool session logs — and normalizes them into one canonical vocabulary. Nothing downstream can invent authorship it wasn't given."],
  ["Store", "SQLite by default; a local file on your disk. Holds raw facts, derived analysis, and their rollups. No server required."],
  ["Analyze", "Derives structural, historical, and coupling facts — complexity, churn, dependency graphs, ownership — from the stored primitives."],
  ["Scoring", "Combines analysis into explainable risk, decomposed into AI-authored vs human-authored shares. Never asserts causation; never emits a number without its evidence chain."],
  ["Interfaces", "Surfaces everything to humans (CLI, HTML report, dashboard, SARIF) and to AI agents (a machine-readable API). Read-only over the store."],
  ["Trust", "Auth, repo-clone sandboxing, rate limiting, secure defaults, zero telemetry, reproducibility — wraps every other layer and is never bypassed by a convenience default."],
] as const;

export default function ArchitecturePage() {
  return (
    <>
      <PageHeader
        crumb="// how it's built"
        title={<>A local-first pipeline you can trust.</>}
        sub="No layer can produce a claim it cannot trace back to a fact in the store. Scores are a derived, fully-decomposed view over evidence — down to the raw git blob or metric snapshot that produced them."
      />
      <main className="mx-auto max-w-5xl px-6">
        <section className="py-14">
          <ol className="space-y-3">
            {LAYERS.map(([name, body], i) => (
              <li key={name} className="flex gap-4 rounded-sm border border-line bg-card p-5">
                <span className="shrink-0 text-sm text-accent">L{i + 1}</span>
                <div>
                  <h2 className="mb-1 font-bold">{name}</h2>
                  <p className="text-[13px] leading-relaxed text-secondary">{body}</p>
                </div>
              </li>
            ))}
          </ol>
          <p className="mt-8 text-sm text-mute">
            Data flows in one direction: interfaces depend on scoring, scoring on analysis,
            analysis on the store, the store on ingest. Nothing flows upward — which is what
            keeps ingest honest.
          </p>
        </section>
      </main>
    </>
  );
}
