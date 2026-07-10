import type { Metadata } from "next";
import { PageHeader } from "@/components/page-header";

export const metadata: Metadata = {
  title: "Install · project-mri",
  description: "Install project-mri with pipx, pip, or Docker. Local-first — no account, no telemetry.",
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
              {l.startsWith("#") ? (
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

export default function InstallPage() {
  return (
    <>
      <PageHeader
        crumb="// five-minute setup"
        title={<>Install once, run on your own machine.</>}
        sub="Self-hosted by default. No SaaS, no telemetry, no account registration. Python only — the dashboard ships as static assets, so there is no Node runtime to install."
      />
      <main className="mx-auto max-w-5xl space-y-8 px-6 py-14">
        <section className="space-y-3">
          <h2 className="text-xs tracking-widest text-mute">/// recommended (pipx)</h2>
          <CodeBlock title="install.sh" lines={["pipx install project-mri", "mri --version"]} />
        </section>

        <section className="space-y-3">
          <h2 className="text-xs tracking-widest text-mute">/// with pip</h2>
          <CodeBlock title="install.sh" lines={["python3 -m pip install --user project-mri"]} />
        </section>

        <section className="space-y-3">
          <h2 className="text-xs tracking-widest text-mute">/// with Docker</h2>
          <CodeBlock
            title="docker.sh"
            lines={[
              "docker run -d --name project-mri -p 7331:7331 \\",
              "  -e MRI_API_KEYS=change-me \\",
              "  ghcr.io/veter391/project-mri:latest",
            ]}
          />
        </section>

        <section className="space-y-3">
          <h2 className="text-xs tracking-widest text-mute">/// first scan</h2>
          <CodeBlock
            title="quickstart.sh"
            lines={[
              "# initialize (creates your admin user + local db)",
              "mri init",
              "# scan a local repository",
              "mri scan /path/to/your/code",
              "# serve the API + dashboard at http://localhost:7331",
              "mri serve",
            ]}
          />
          <p className="text-sm text-mute">
            Reports are written locally. When exposed on a public interface, project-mri
            fail-closes without authentication — set an API key or a dashboard user first.
          </p>
        </section>
      </main>
    </>
  );
}
