import type { Metadata } from "next";
import { PageHeader } from "@/components/page-header";

const GITHUB = "https://github.com/veter391/project-mri";

export const metadata: Metadata = {
  title: "Self-host · project-mri",
  description:
    "Run project-mri on your own machine end to end: install, init, serve, open the dashboard, scan a repo. Local-first, zero telemetry — your code never leaves your machine.",
};

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
                " "
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

const STEPS = [
  {
    n: "01",
    title: "Install",
    body: "One Python package. The dashboard ships as pre-built static assets, so there is no Node runtime to install.",
    block: { title: "install.sh", lines: ["pipx install project-mri", "mri --version"] },
  },
  {
    n: "02",
    title: "Initialize",
    body: "Creates your admin user and a local database. You are prompted for a username, a password (8+ characters), and a config path. Idempotent — safe to re-run.",
    block: { title: "init.sh", lines: ["mri init"] },
  },
  {
    n: "03",
    title: "Serve",
    body: "Binds to 127.0.0.1:7331 by default — local-only, no auth needed on loopback. Then open the dashboard in your browser.",
    block: {
      title: "serve.sh",
      lines: ["mri serve", "# then open http://localhost:7331/dashboard/"],
    },
  },
  {
    n: "04",
    title: "Scan a repository",
    body: "Point it at a local directory or a git URL. A remote URL is shallow-cloned into a sandbox and cleaned up afterward. The report is written to your local cache.",
    block: {
      title: "scan.sh",
      lines: [
        "# scan a local checkout",
        "mri scan /path/to/your/code",
        "",
        "# or a remote repo (shallow clone, auto-cleanup)",
        "mri scan https://github.com/yourorg/yourrepo.git",
      ],
    },
  },
] as const;

const GUARANTEES = [
  [
    "Your code never leaves your machine",
    "No SaaS, no account, no phone-home. The only network access is what you explicitly ask for — cloning a repo URL you named, or a webhook you configured.",
  ],
  [
    "Zero telemetry, proven not asserted",
    "A test replaces the socket layer and fails the build if any code path opens a non-loopback connection. The suite runs a full local scan and a full session-log ingest with the network sealed.",
  ],
  [
    "Fail-closed when exposed",
    "Bind to a public interface without configuring auth and the server refuses to start, rather than serving in the open. Loopback stays frictionless; everything else needs an API key or a dashboard user.",
  ],
] as const;

const DOCS = [
  ["INSTALL.md", "Full install matrix — pipx, pip, Docker, and from source", "/blob/main/docs/INSTALL.md"],
  ["CONFIG.md", "The complete .mri.yml reference", "/blob/main/docs/CONFIG.md"],
  ["DASHBOARD.md", "Using the self-hosted dashboard", "/blob/main/docs/DASHBOARD.md"],
  ["TRUST.md", "Every guarantee, mapped to the code or test that proves it", "/blob/main/docs/TRUST.md"],
] as const;

export default function SelfHostPage() {
  return (
    <>
      <PageHeader
        crumb="// run it yourself"
        title={
          <>
            Self-host in <span className="text-accent">four commands</span>.
          </>
        }
        sub="project-mri is self-hosted by default — the whole experience runs on your own machine or server. Install, initialize, serve, scan. No account, no telemetry, no cloud dependency."
      />
      <main className="mx-auto max-w-5xl space-y-12 px-6 py-14">
        <section className="space-y-6">
          <h2 className="text-xs tracking-widest text-mute">/// the walkthrough</h2>
          <ol className="space-y-6">
            {STEPS.map((step) => (
              <li key={step.n} className="grid gap-4 sm:grid-cols-[1fr_1.4fr] sm:items-start">
                <div>
                  <div className="mb-2 text-xs text-accent">{step.n}</div>
                  <h3 className="mb-2 font-bold">{step.title}</h3>
                  <p className="text-[13px] leading-relaxed text-secondary">{step.body}</p>
                </div>
                <CodeBlock title={step.block.title} lines={[...step.block.lines]} />
              </li>
            ))}
          </ol>
        </section>

        <section className="space-y-4 border-t border-line pt-12">
          <h2 className="text-xs tracking-widest text-mute">/// the local-first guarantee</h2>
          <div className="grid gap-px overflow-hidden rounded-sm border border-line bg-line sm:grid-cols-3">
            {GUARANTEES.map(([title, body]) => (
              <article key={title} className="bg-deep p-6">
                <h3 className="mb-2 font-bold text-accent">{title}</h3>
                <p className="text-[13px] leading-relaxed text-secondary">{body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="space-y-4 border-t border-line pt-12">
          <h2 className="text-xs tracking-widest text-mute">/// exposing it on a network</h2>
          <p className="max-w-3xl text-[13px] leading-relaxed text-secondary">
            To reach the dashboard from another host, bind to all interfaces and put it behind a
            reverse proxy. Because the server fails closed on a non-loopback bind, you must
            configure auth first — set an API key or create a dashboard user with{" "}
            <code className="text-accent">mri init</code>.
          </p>
          <CodeBlock
            title="expose.sh"
            lines={[
              "# requires auth to be configured, or it refuses to start",
              "MRI_HOST=0.0.0.0 mri serve",
            ]}
          />
        </section>

        <section className="space-y-4 border-t border-line pt-12">
          <h2 className="text-xs tracking-widest text-mute">/// go deeper</h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {DOCS.map(([name, desc, path]) => (
              <li key={name}>
                <a
                  href={`${GITHUB}${path}`}
                  className="block rounded-sm border border-line bg-card p-5 transition-colors hover:border-accent/40"
                >
                  <div className="mb-1 text-sm text-accent">{name} ↗</div>
                  <p className="text-[13px] leading-relaxed text-secondary">{desc}</p>
                </a>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </>
  );
}
