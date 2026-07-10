import type { Metadata } from "next";
import { PageHeader } from "@/components/page-header";

export const metadata: Metadata = {
  title: "Roadmap · project-mri",
  description: "From a working CLI and dashboard to decision provenance and agent-native intelligence.",
};

const PHASES = [
  ["Now", "Core engine", "Git-history + structure analyzers, explainable scoring, CLI, self-contained HTML reports, SARIF, and a self-hosted dashboard.", "shipping"],
  ["Next", "AI-authorship attribution", "Ingest local AI-tool session logs to decompose per-file risk into AI-authored vs human-authored shares, with an ai_influence score.", "in progress"],
  ["Then", "Decision provenance", "Link commits, PRs, issues, and architectural decisions into a queryable why-graph — the reason behind every refactor.", "planned"],
  ["Later", "Agent-native (MCP)", "Expose the codebase-intelligence model over MCP so coding agents can query risk, history, and decisions live.", "planned"],
] as const;

const BADGE: Record<string, string> = {
  shipping: "text-ok",
  "in progress": "text-warn",
  planned: "text-mute",
};

export default function RoadmapPage() {
  return (
    <>
      <PageHeader
        crumb="// where this is going"
        title={<>From code health to decision intelligence.</>}
        sub="Every phase delivers real value on its own. We prioritize what solves a painful problem, stays local-first and transparent, and is technically honest."
      />
      <main className="mx-auto max-w-5xl px-6 py-14">
        <ol className="space-y-3">
          {PHASES.map(([when, title, body, status]) => (
            <li key={title} className="rounded-sm border border-line bg-card p-6">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs tracking-widest text-accent">{when}</span>
                <span className={`text-[11px] ${BADGE[status]}`}>{status}</span>
              </div>
              <h2 className="mb-2 font-bold">{title}</h2>
              <p className="text-[13px] leading-relaxed text-secondary">{body}</p>
            </li>
          ))}
        </ol>
      </main>
    </>
  );
}
