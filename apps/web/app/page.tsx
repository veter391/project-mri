const GITHUB = "https://github.com/veter391/project-mri";

const PRINCIPLES = [
  ["01", "Facts over magic scores", "Every score decomposes into named, traceable signals. Nothing you can't audit."],
  ["02", "Local-first, always", "Reads your local .git. No account, no upload, no telemetry by default."],
  ["03", "Explain before recommend", "Lead with the data and the risk. You stay the decision-maker."],
  ["04", "Open core, forever", "MIT. Fork it, ship it inside your company, build on it."],
] as const;

const ANALYZERS = [
  ["git_history", "Churn, hotspots, ownership and bus factor mined from the full commit history."],
  ["architecture", "Modularity and structural health of the current codebase."],
  ["dependencies", "Import graph, cycles, and blast radius."],
  ["complexity", "Cyclomatic and size signals per file and function."],
  ["tech_debt", "Debt markers weighted against size — where cleanup pays off."],
  ["coupling", "Afferent/efferent coupling, instability, and drift over time."],
] as const;

export default function Home() {
  return (
    <main className="mx-auto max-w-5xl px-6">
      <section className="py-24 sm:py-32">
        <p className="mb-5 text-xs tracking-widest text-accent">
          // codebase intelligence · built for the AI coding era
        </p>
        <h1 className="max-w-3xl text-4xl font-bold leading-tight sm:text-6xl">
          An <span className="text-accent">MRI</span> for your codebase.
        </h1>
        <p className="mt-6 max-w-2xl text-base leading-relaxed text-secondary sm:text-lg">
          An open-source engine that x-rays a repository — mining its Git history and
          structure into explainable, auditable health scores that reveal hotspots,
          complexity, single-owner risk, and the fingerprint of AI-generated code.
        </p>

        <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="inline-flex items-center gap-3 rounded-sm border border-line-2 bg-card px-4 py-3 text-sm">
            <span className="text-accent">$</span>
            <code>pipx install project-mri</code>
          </div>
          <a
            href={GITHUB}
            className="inline-flex items-center gap-2 rounded-sm border border-accent/40 px-4 py-3 text-sm text-accent transition-colors hover:bg-accent/10"
          >
            View on GitHub →
          </a>
        </div>
      </section>

      <section className="border-t border-line py-16">
        <h2 className="mb-8 text-xs tracking-widest text-mute">/// principles</h2>
        <div className="grid gap-px overflow-hidden rounded-sm border border-line bg-line sm:grid-cols-2">
          {PRINCIPLES.map(([n, title, body]) => (
            <div key={n} className="bg-deep p-6">
              <div className="mb-2 text-xs text-accent">{n}</div>
              <div className="mb-2 font-bold">{title}</div>
              <p className="text-sm leading-relaxed text-secondary">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-t border-line py-16">
        <h2 className="mb-2 text-xs tracking-widest text-mute">/// six analyzers</h2>
        <p className="mb-8 max-w-2xl text-sm text-secondary">
          Each extracts one slice of truth; the scoring engine combines them into
          explainable risk. Every score links to the data behind it.
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {ANALYZERS.map(([name, desc]) => (
            <div
              key={name}
              className="rounded-sm border border-line bg-card p-5 transition-colors hover:border-accent/40"
            >
              <div className="mb-2 text-sm text-accent">{name}</div>
              <p className="text-[13px] leading-relaxed text-secondary">{desc}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
