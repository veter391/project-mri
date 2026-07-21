import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { LinkCard } from "@/components/ui/card";
import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: "Docs — Install, Run, and Understand MRI",
  description:
    "The MRI documentation index: quickstart, CLI reference, MCP server, SARIF CI gate, session-log setup, self-hosting, and architecture. Every page links to the real in-repo source.",
  alternates: { canonical: "/docs" },
};

const GH = SITE.github;

const GROUPS = [
  {
    crumb: "01",
    title: "Getting started",
    blurb: "Install it, run your first scan, stand it up on your own machine.",
    links: [
      { href: "/docs/quickstart", title: "Quickstart", desc: "Install, mri scan ., mri serve, first report — in five minutes." },
      { href: "/docs/self-hosting", title: "Self-hosting", desc: "Run the full dashboard + backend locally. Local-first by default." },
      { href: `${GH}/blob/main/docs/CONFIG.md`, title: "CONFIG.md", desc: "The complete .mri.yml reference — every key and default." },
    ],
  },
  {
    crumb: "02",
    title: "Understanding it",
    blurb: "How the scores are computed, and what MRI guarantees.",
    links: [
      { href: `${GH}/blob/main/docs/METHODOLOGY.md`, title: "METHODOLOGY.md", desc: "How git history + structure become explainable, decomposable scores." },
      { href: `${GH}/blob/main/docs/TRUST.md`, title: "TRUST.md", desc: "Every guarantee mapped to the code or test that proves it." },
      { href: "/how-it-works", title: "How it works", desc: "The five-stage loop, with real module paths and OSS credits." },
    ],
  },
  {
    crumb: "03",
    title: "Reference",
    blurb: "The surfaces you build against.",
    links: [
      { href: "/docs/cli", title: "CLI reference", desc: "Every mri subcommand — matched to the real CLI, no aspirational commands." },
      { href: "/docs/mcp", title: "MCP server", desc: "The tools MRI exposes to agents, and how to point Claude Code / Cursor at it." },
      { href: "/docs/ci", title: "SARIF CI gate", desc: "Gate a pull request on risk with GitHub Actions or GitLab CI." },
      { href: "/docs/session-log-setup", title: "Session-log setup", desc: "Point MRI at ~/.claude and ~/.cursor — privacy notes included." },
    ],
  },
  {
    crumb: "04",
    title: "Project",
    blurb: "The decisions and architecture behind the build.",
    links: [
      { href: "/docs/architecture", title: "Architecture", desc: "The module map: analyzers, api, services, db, cli." },
      { href: `${GH}/tree/main/docs/adr`, title: "Decision records", desc: "The full set of ADRs behind the stack and the license." },
      { href: `${GH}/blob/main/docs/AUDIT.md`, title: "AUDIT.md", desc: "The security and correctness audit — what was checked, and found." },
    ],
  },
] as const;

export default function DocsPage() {
  return (
    <>
      <PageHeader
        eyebrow="documentation"
        title="Read the source of truth."
        lede="Every page here links to the real, in-repo documentation on GitHub — nothing is duplicated or paraphrased. Start with the quickstart, then go as deep as the decision records."
      />
      <Section>
        <Container>
          <div className="flex flex-col gap-14">
            {GROUPS.map((g) => (
              <section key={g.title}>
                <div className="flex items-baseline gap-3">
                  <span className="text-accent font-mono text-mono-sm">{g.crumb}</span>
                  <h2 className="text-mute font-sans text-caption font-medium tracking-[0.1em] uppercase">
                    {g.title}
                  </h2>
                </div>
                <p className="text-secondary mt-3 max-w-[62ch] font-body text-body">
                  {g.blurb}
                </p>
                <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {g.links.map((l) => (
                    <LinkCard key={l.title} href={l.href} title={l.title}>
                      {l.desc}
                    </LinkCard>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </Container>
      </Section>
    </>
  );
}
