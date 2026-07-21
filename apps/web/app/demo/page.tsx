import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "@/components/page-header";

const GITHUB = "https://github.com/veter391/project-mri";

export const metadata: Metadata = {
  title: "Demo · project-mri",
  description:
    "There is no hosted live demo yet — deployment is owner-gated. Instead, run `mri demo` locally to generate a full sample report with no real scan, and see exactly what a report shows.",
};

// A shared code block, matching the self-host page. `$`-prefixed lines are
// commands; `#`-prefixed lines are comments. Everything else is plain.
function CodeBlock({ title, lines }: { title: string; lines: string[] }) {
  return (
    <div className="overflow-hidden rounded-sm border border-line-2 bg-card">
      <div className="flex items-center justify-between border-b border-line px-4 py-2 text-[11px] text-mute">
        <span>{title}</span>
        <span>bash</span>
      </div>
      <pre className="overflow-x-auto px-4 py-3 text-[13px] leading-relaxed">
        <code>
          {lines.map((l, i) => (
            <span key={i} className="block">
              {l === "" ? (
                " "
              ) : l.startsWith("#") ? (
                <span className="text-mute">{l}</span>
              ) : (
                <>
                  <span className="text-accent">$ </span>
                  {l}
                </>
              )}
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}

// A static, clearly-labelled terminal mock of `mri demo` output. Not a live
// widget — the leading marks mirror the real CLI (→ status, ✓ success).
const MOCK_OUTPUT: string[] = [
  "$ mri demo",
  "→ generating demo report for 'my-legacy-app'",
  "✓ demo report saved → ./mri-demo-report.html",
  "  overall health: 61.4/100 (fair)",
  "",
  "# open ./mri-demo-report.html in a browser to explore the full report",
];

const REPORT_SHOWS = [
  [
    "Explainable health scores",
    "One overall health band, decomposed into named signals — hotspots, complexity, single-owner risk. Every score carries the formula and the exact commits and files behind it.",
  ],
  [
    "Hotspots and ownership",
    "The files that churn hardest, who owns them, and where the bus factor is dangerously low. Ranked, not hand-waved — each row links back to its git evidence.",
  ],
  [
    "The fusion view",
    "Where code-health signals meet AI-authorship. Per-file AI-authored, human-authored, and unattributed shares, traced to the local agent sessions that produced them.",
  ],
  [
    "Decision → consequence",
    "A recorded decision linked to the measured change that followed it. Framed as correlation, never causation — the report says so in plain language.",
  ],
] as const;

const RUN_IT = {
  title: "run-it-yourself.sh",
  lines: [
    "# 1. install (no Node runtime needed — the dashboard ships pre-built)",
    "pipx install project-mri",
    "",
    "# 2. generate a full sample report — no real scan, no network",
    "mri demo",
    "",
    "# optional: name the demo project and output path",
    "mri demo --slug my-legacy-app -o ./mri-demo-report.html",
  ],
};

export default function DemoPage() {
  return (
    <>
      <PageHeader
        crumb="// see it in action"
        title={
          <>
            No live server yet — <span className="text-accent">run the demo locally</span>.
          </>
        }
        sub="A hosted, interactive demo is coming once the project is deployed — deployment is deliberately owner-gated for now. Until then, one command generates a complete sample report on your own machine, with no real scan and no network access."
      />
      <main className="mx-auto max-w-5xl space-y-12 px-6 py-14">
        <section>
          <div className="rounded-sm border border-warn/30 bg-warn/5 p-6">
            <div className="mb-2 font-bold text-warn">Honest note: this is not a live instance.</div>
            <p className="max-w-3xl text-sm leading-relaxed text-secondary">
              We are not faking a hosted demo. There is no deployed instance to click through yet,
              so nothing on this page is a live widget. The terminal output below is a static mock
              of what <code className="text-accent">mri demo</code> prints — everything real happens
              on your machine when you run the command yourself. A hosted demo will land here once
              deployment is unblocked.
            </p>
          </div>
        </section>

        <section className="space-y-4">
          <h2 className="text-xs tracking-widest text-mute">/// what `mri demo` does</h2>
          <p className="max-w-3xl text-sm leading-relaxed text-secondary">
            <code className="text-accent">mri demo</code> generates a deterministic, realistic
            report for a fake <code className="text-accent">my-legacy-app</code> project — the same
            shape as a real scan, with plausible-but-pessimistic legacy numbers, so you see what the
            output looks like without pointing it at any repository. It scans nothing, clones
            nothing, and reaches no network. It just writes an HTML report you can open in a browser.
          </p>
          <figure className="overflow-hidden rounded-sm border border-line-2 bg-card">
            <figcaption className="flex items-center justify-between border-b border-line px-4 py-2 text-[11px] text-mute">
              <span>mri demo · illustrative output (static mock)</span>
              <span>terminal</span>
            </figcaption>
            <pre className="overflow-x-auto px-4 py-3 text-[13px] leading-relaxed">
              <code>
                {MOCK_OUTPUT.map((l, i) => (
                  <span key={i} className="block">
                    {l === "" ? (
                      " "
                    ) : l.startsWith("$") ? (
                      <>
                        <span className="text-accent">$ </span>
                        {l.slice(2)}
                      </>
                    ) : l.startsWith("#") ? (
                      <span className="text-mute">{l}</span>
                    ) : l.startsWith("✓") ? (
                      <span className="text-ok">{l}</span>
                    ) : (
                      <span className="text-secondary">{l}</span>
                    )}
                  </span>
                ))}
              </code>
            </pre>
          </figure>
          <p className="text-[12px] text-mute">
            Numbers are illustrative. The real command produces deterministic values from a seed —
            yours will match on the same slug.
          </p>
        </section>

        <section className="space-y-4 border-t border-line pt-12">
          <h2 className="text-xs tracking-widest text-mute">/// what the report shows</h2>
          <p className="max-w-3xl text-sm leading-relaxed text-secondary">
            The demo report has the same anatomy as a real one. In one sentence, that anatomy is:{" "}
            <span className="text-ink">
              a percentage of the code is AI-authored, traced back to the sessions that wrote it, and
              each recorded decision is linked to the consequence that followed
            </span>{" "}
            — all of it decomposable to the underlying commits and files.
          </p>
          <div className="grid gap-px overflow-hidden rounded-sm border border-line bg-line sm:grid-cols-2">
            {REPORT_SHOWS.map(([title, body]) => (
              <article key={title} className="bg-deep p-6">
                <h3 className="mb-2 font-bold text-accent">{title}</h3>
                <p className="text-[13px] leading-relaxed text-secondary">{body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="space-y-4 border-t border-line pt-12">
          <h2 className="text-xs tracking-widest text-mute">/// run it yourself</h2>
          <p className="max-w-3xl text-[13px] leading-relaxed text-secondary">
            Two commands: install the package, then generate the sample report. When you are ready to
            point it at real code, the self-host guide walks through init, serve, and scan.
          </p>
          <CodeBlock title={RUN_IT.title} lines={RUN_IT.lines} />
          <div className="flex flex-wrap gap-3 pt-2">
            <Link
              href="/self-host"
              className="inline-flex items-center gap-2 rounded-sm border border-accent/40 px-4 py-3 text-sm text-accent transition-colors hover:bg-accent/10"
            >
              Self-host it for real →
            </Link>
            <Link
              href="/docs"
              className="inline-flex items-center gap-2 rounded-sm border border-line px-4 py-3 text-sm text-secondary transition-colors hover:border-accent/40 hover:text-accent"
            >
              Read the docs →
            </Link>
            <a
              href={GITHUB}
              className="inline-flex items-center gap-2 rounded-sm border border-line px-4 py-3 text-sm text-secondary transition-colors hover:border-accent/40 hover:text-accent"
            >
              View on GitHub ↗
            </a>
          </div>
        </section>
      </main>
    </>
  );
}
