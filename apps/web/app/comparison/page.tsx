import type { Metadata } from "next";
import { PageHeader } from "@/components/page-header";

const GITHUB = "https://github.com/veter391/project-mri";

export const metadata: Metadata = {
  title: "Comparison · project-mri",
  description:
    "An honest comparison of project-mri with Repowise, GitIntel-MCP, and the code-maat/CodeScene lineage — license, local-first, AI attribution, decision provenance, and MCP.",
};

// Verdict vocabulary. Never color-only: every cell carries a text label.
type Verdict = "yes" | "no" | "partial";

const VERDICT_STYLE: Record<Verdict, string> = {
  yes: "text-ok",
  no: "text-alert",
  partial: "text-warn",
};

const VERDICT_MARK: Record<Verdict, string> = {
  yes: "✓",
  no: "✕",
  partial: "~",
};

type Cell = { v: Verdict; note: string };

const TOOLS = ["project-mri", "Repowise", "GitIntel-MCP", "CodeScene"] as const;

const ROWS: { capability: string; cells: [Cell, Cell, Cell, Cell] }[] = [
  {
    capability: "License",
    cells: [
      { v: "yes", note: "MIT, forever — no paid tier, no open-core split" },
      { v: "partial", note: "AGPL-3.0 open core + paid/hosted tiers" },
      { v: "yes", note: "MIT" },
      { v: "no", note: "Commercial, paid — code-maat ancestor is OSS" },
    ],
  },
  {
    capability: "Runs fully local · zero telemetry",
    cells: [
      { v: "yes", note: "No account, no beacon — a build-failing egress test proves it" },
      { v: "partial", note: "Open core is local; hosted/paid features are not" },
      { v: "yes", note: "Local MCP server, no telemetry" },
      { v: "no", note: "SaaS or paid on-prem" },
    ],
  },
  {
    capability: "Git-history mining · hotspots · ownership",
    cells: [
      { v: "yes", note: "Churn, hotspots, bus factor, coupling over full history" },
      { v: "yes", note: "Core capability" },
      { v: "yes", note: "Git intelligence over commit history" },
      { v: "yes", note: "Pioneered behavioral-code / hotspot analysis" },
    ],
  },
  {
    capability: "Explainable, decomposable scores",
    cells: [
      { v: "yes", note: "Every score → formula + exact commits/files + confidence" },
      { v: "yes", note: "Explainable scoring is part of its pitch" },
      { v: "partial", note: "Surfaces signals; less score decomposition" },
      { v: "yes", note: "Explains hotspots and health metrics" },
    ],
  },
  {
    capability: "Session-log · prompt-level AI attribution",
    cells: [
      { v: "yes", note: "Ingests local agent session logs; content off by default" },
      { v: "no", note: "Git-metadata authorship only — not prompt-level" },
      { v: "no", note: "Not an AI-authorship tool" },
      { v: "no", note: "Not an AI-authorship tool" },
    ],
  },
  {
    capability: "Decision → consequence loop",
    cells: [
      { v: "yes", note: "Links a recorded decision to its later measured effect — correlational, never causal" },
      { v: "partial", note: "Ships a decision-provenance graph, but not consequence tracking" },
      { v: "no", note: "Out of scope" },
      { v: "no", note: "Out of scope" },
    ],
  },
  {
    capability: "MCP server for AI agents",
    cells: [
      { v: "yes", note: "Read-only MCP over the intelligence model" },
      { v: "yes", note: "Ships a 9-tool MCP" },
      { v: "yes", note: "It is an MCP server by design" },
      { v: "no", note: "No MCP surface" },
    ],
  },
];

const DIFFERENTIATORS = [
  [
    "Session-log, prompt-level attribution",
    "We read local AI-tool session logs to decompose per-file risk into AI-authored vs human-authored shares. Repowise attributes from git metadata only. Session content stays off by default — logs can hold secrets.",
  ],
  [
    "Decision → consequence loop",
    "Record a decision, then link it to the measured consequence that followed. We frame it as correlation and never assert causation — but no other peer closes this loop today.",
  ],
  [
    "True MIT, forever · zero telemetry",
    "No AGPL, no paid tier, no analytics beacon anywhere in the core. The zero-telemetry claim is executable: a test fails the build if any code path opens a non-loopback connection.",
  ],
  [
    "Explainability-first",
    "Every score decomposes into named signals with the formula, the exact commits and files behind it, a confidence value, and a plain 'could be wrong because' caveat. Nothing you can't audit.",
  ],
] as const;

const CAVEATS = [
  "“Nobody does this” is false. Repowise already fuses git-mining, explainable scores, a decision-provenance graph, and a 9-tool MCP — it is the real wall, not a strawman.",
  "CodeScene is more mature at behavioral code analysis and has years of research behind the hotspot model. We build on that lineage (via code-maat); we did not invent it.",
  "Structural coupling analysis is turnkey only for Python today. “Language-agnostic” is honest only for git-history and co-change signals — we do not overstate the rest.",
  "We position on execution and trust, not novelty. The honest read of the idea is strong-but-not-unique; the goal is to be the best-executed, most-trusted, truly-free option — stated plainly.",
];

export default function ComparisonPage() {
  return (
    <>
      <PageHeader
        crumb="// how it compares"
        title={
          <>
            An honest look at the <span className="text-accent">neighborhood</span>.
          </>
        }
        sub="We are not the only tool that mines Git history or ships an MCP. This page states, cell by cell, where a peer does something we don't — and where our differences are real. Every claim here is one we can defend."
      />
      <main className="mx-auto max-w-5xl space-y-12 px-6 py-14">
        <section>
          <h2 className="mb-3 text-xs tracking-widest text-mute">/// the honest framing</h2>
          <p className="max-w-3xl text-sm leading-relaxed text-secondary">
            The closest peer is <span className="text-ink">Repowise</span> (AGPL + paid
            open-core), which already fuses most of the same pillars. The real white space is
            narrow and specific: session-log, prompt-level AI attribution fused with code-health
            signals, a decision-to-consequence loop, and a genuinely permissive MIT-forever
            license with zero telemetry. We compete on execution and trust, not on a claim that
            no one else is in this space.
          </p>
        </section>

        <section>
          <h2 className="mb-4 text-xs tracking-widest text-mute">/// capability matrix</h2>
          <div className="overflow-x-auto rounded-sm border border-line">
            <table className="w-full border-collapse text-left text-[13px]">
              <caption className="sr-only">
                Capability comparison of project-mri, Repowise, GitIntel-MCP, and CodeScene
              </caption>
              <thead>
                <tr className="border-b border-line bg-raised">
                  <th scope="col" className="p-3 font-bold text-mute">
                    Capability
                  </th>
                  {TOOLS.map((t) => (
                    <th
                      key={t}
                      scope="col"
                      className={`p-3 font-bold ${t === "project-mri" ? "text-accent" : "text-ink"}`}
                    >
                      {t}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROWS.map((row) => (
                  <tr key={row.capability} className="border-b border-line last:border-b-0">
                    <th scope="row" className="p-3 align-top font-normal text-secondary">
                      {row.capability}
                    </th>
                    {row.cells.map((cell, i) => (
                      <td key={TOOLS[i]} className="p-3 align-top">
                        <span className={`mr-2 font-bold ${VERDICT_STYLE[cell.v]}`}>
                          <span aria-hidden="true">{VERDICT_MARK[cell.v]}</span>
                          <span className="sr-only">{cell.v}. </span>
                        </span>
                        <span className="text-[12px] leading-relaxed text-secondary">
                          {cell.note}
                        </span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[12px] text-mute">
            <span className="text-ok">✓</span> yes &nbsp;·&nbsp;
            <span className="text-warn">~</span> partial &nbsp;·&nbsp;
            <span className="text-alert">✕</span> no. Peer capabilities as understood from public
            sources; corrections welcome via an issue on GitHub.
          </p>
        </section>

        <section>
          <h2 className="mb-4 text-xs tracking-widest text-mute">
            /// where we are genuinely different
          </h2>
          <div className="grid gap-px overflow-hidden rounded-sm border border-line bg-line sm:grid-cols-2">
            {DIFFERENTIATORS.map(([title, body]) => (
              <article key={title} className="bg-deep p-6">
                <h3 className="mb-2 font-bold text-accent">{title}</h3>
                <p className="text-sm leading-relaxed text-secondary">{body}</p>
              </article>
            ))}
          </div>
        </section>

        <section>
          <h2 className="mb-4 text-xs tracking-widest text-mute">
            /// what we do not claim
          </h2>
          <ul className="space-y-3">
            {CAVEATS.map((c) => (
              <li key={c} className="flex gap-3 text-sm leading-relaxed text-secondary">
                <span aria-hidden="true" className="text-accent">
                  —
                </span>
                <span>{c}</span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <div className="rounded-sm border border-accent/30 bg-accent/5 p-6">
            <div className="mb-2 font-bold text-accent">Read the guarantees, not the pitch.</div>
            <p className="mb-4 max-w-2xl text-sm text-secondary">
              Every claim on this page maps to code or a test in the repository. Audit it
              yourself.
            </p>
            <a
              href={GITHUB}
              className="inline-flex items-center gap-2 rounded-sm border border-accent/40 px-4 py-3 text-sm text-accent transition-colors hover:bg-accent/10"
            >
              View on GitHub →
            </a>
          </div>
        </section>
      </main>
    </>
  );
}
