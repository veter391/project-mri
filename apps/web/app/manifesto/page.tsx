import type { Metadata } from "next";
import { PageHeader } from "@/components/page-header";

export const metadata: Metadata = {
  title: "Manifesto · project-mri",
  description: "Facts over magic scores. Local-first. Explain before recommend. Open core forever.",
};

const PRINCIPLES = [
  ["01", "Facts over magic scores", "A composite score is only useful if you can decompose it. If architecture_health = 71, you should see why — a tree of named, traceable signals, not a black box. We will never ship a number you can't audit."],
  ["02", "Local-first, always", "Your code is yours. We never phone home, never require a login, never bundle telemetry by default. The database is a regular file on your disk — readable, exportable, deletable."],
  ["03", "Explain before recommend", "Most tools lead with recommendations. We lead with data: the architecture, the trends, the risk signals — and only then offer suggestions. You should be able to disagree with the recommendation and still understand the analysis."],
  ["04", "Open core, forever", "The analyzers, the scoring, the report generators — all MIT. Fork it. Audit it. Ship it inside your company. The license will not change without community consent."],
] as const;

const NON_GOALS = [
  "Real-time monitoring / runtime observability — use Prometheus, Datadog, OpenTelemetry.",
  "Security vulnerability scanning — Trivy, Snyk, and Dependabot do this better.",
  "Replacing SonarQube — different focus: we measure architecture and history, not style.",
  "Automatic refactoring — we tell you what's risky; we never silently modify your code.",
  "Cloud-hosted SaaS by default — the core stays local; any cloud feature is opt-in.",
];

export default function ManifestoPage() {
  return (
    <>
      <PageHeader
        crumb="// principles"
        title={<>Facts over magic scores. Local-first. Explain before recommend.</>}
        sub="Four principles that decide every design decision in project-mri. Read them. Question them. Hold us to them."
      />
      <main className="mx-auto max-w-5xl px-6">
        <section className="py-14">
          <div className="grid gap-px overflow-hidden rounded-sm border border-line bg-line sm:grid-cols-2">
            {PRINCIPLES.map(([n, title, body]) => (
              <article key={n} className="bg-deep p-6">
                <div className="mb-2 text-xs text-accent">{n}</div>
                <h2 className="mb-2 font-bold">{title}</h2>
                <p className="text-sm leading-relaxed text-secondary">{body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="border-t border-line py-14">
          <h2 className="mb-6 text-xs tracking-widest text-mute">/// what we won&apos;t build</h2>
          <ul className="space-y-3">
            {NON_GOALS.map((g) => (
              <li key={g} className="flex gap-3 text-sm leading-relaxed text-secondary">
                <span className="text-alert">✕</span>
                <span>{g}</span>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </>
  );
}
