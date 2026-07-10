import type { Metadata } from "next";
import { PageHeader } from "@/components/page-header";

export const metadata: Metadata = {
  title: "Features · project-mri",
  description: "Six layers of codebase intelligence: Git history, structure, graphs, explainable scoring, AI impact, and outputs.",
};

const LAYERS = [
  ["01 · git history", "Mines the full commit history: churn over 30/90/365-day windows, change frequency, ownership evolution, co-change patterns, and hotspots — high recent activity crossed with complexity."],
  ["02 · code structure", "Parses the current codebase with tree-sitter into a real AST — modules, imports, call graphs, and complexity metrics — multi-language, not regex guessing."],
  ["03 · graphs", "Combines history and structure into dependency, call, evolution, and knowledge graphs. Each answers a different question about the system."],
  ["04 · scoring & risk", "Composite, explainable scores — architecture health, tech debt, bus factor, knowledge islands, coupling evolution. Click any score, see the contributing signals, drill into the files."],
  ["05 · AI impact", "Detects and frames the influence of AI coding tools on the codebase — an ai_influence signal from commit patterns and, optionally, local session logs. Descriptive, never causal."],
  ["06 · output layer", "CLI summary, a self-contained HTML report, a self-hosted dashboard, SARIF for CI, and machine-readable JSON for tooling and AI agents."],
] as const;

export default function FeaturesPage() {
  return (
    <>
      <PageHeader
        crumb="// what it analyzes"
        title={<>Six layers of <span className="text-accent">codebase intelligence</span>.</>}
        sub="Each analyzer extracts one slice of truth. The scoring engine combines them into explainable risk profiles. Every score links to the data behind it — nothing hidden, nothing magic."
      />
      <main className="mx-auto max-w-5xl px-6">
        <section className="grid gap-3 py-14 sm:grid-cols-2">
          {LAYERS.map(([title, body]) => (
            <article
              key={title}
              className="rounded-sm border border-line bg-card p-6 transition-colors hover:border-accent/40"
            >
              <h2 className="mb-3 text-sm text-accent">{title}</h2>
              <p className="text-[13px] leading-relaxed text-secondary">{body}</p>
            </article>
          ))}
        </section>
      </main>
    </>
  );
}
