import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "@/components/page-header";

const GITHUB = "https://github.com/veter391/project-mri";

export const metadata: Metadata = {
  title: "Docs · project-mri",
  description:
    "The project-mri documentation index: install and configure, understand the methodology and trust guarantees, the API and integration reference, and the project's architecture decision records.",
};

// A doc entry is either an in-repo markdown file (opened on GitHub) or an
// on-site page/section that already exists as a route. `gh` is a path under
// docs/ ; `to` is an internal route. Exactly one is set per entry.
type DocLink = {
  name: string;
  desc: string;
  gh?: string;
  to?: string;
};

type DocGroup = {
  crumb: string;
  title: string;
  blurb: string;
  links: DocLink[];
};

// Every `gh` path below was verified to exist in docs/ before being listed.
// ARCHITECTURE.md does not exist as a doc — the on-site /architecture page is
// linked instead. ROADMAP is the ROADMAP-FULL-PRODUCTION.md file in the repo.
const GROUPS: DocGroup[] = [
  {
    crumb: "01",
    title: "Getting started",
    blurb: "Install it, stand it up on your own machine, and configure it.",
    links: [
      {
        name: "INSTALL.md",
        desc: "The full install matrix — pipx, pip, Docker, and from source.",
        gh: "/blob/main/docs/INSTALL.md",
      },
      {
        name: "Self-host guide",
        desc: "Install, initialize, serve, and scan in four commands. Local-first by default.",
        to: "/self-host",
      },
      {
        name: "CONFIG.md",
        desc: "The complete .mri.yml reference — every key, its default, and what it changes.",
        gh: "/blob/main/docs/CONFIG.md",
      },
    ],
  },
  {
    crumb: "02",
    title: "Understanding it",
    blurb: "How the scores are computed, what we guarantee, and how the system is shaped.",
    links: [
      {
        name: "METHODOLOGY.md",
        desc: "How raw Git history and structure become explainable, decomposable health scores.",
        gh: "/blob/main/docs/METHODOLOGY.md",
      },
      {
        name: "TRUST.md",
        desc: "Every guarantee mapped to the code path or test that proves it — including zero telemetry.",
        gh: "/blob/main/docs/TRUST.md",
      },
      {
        name: "Architecture overview",
        desc: "How the scanner, fusion engine, database, API, and MCP surface fit together.",
        to: "/architecture",
      },
    ],
  },
  {
    crumb: "03",
    title: "Reference",
    blurb: "The surfaces you build against — HTTP API, agent integrations, and the dashboard.",
    links: [
      {
        name: "API.md",
        desc: "The HTTP API reference: endpoints, request and response shapes, and auth.",
        gh: "/blob/main/docs/API.md",
      },
      {
        name: "INTEGRATIONS.md",
        desc: "Wiring project-mri into agents, editors, and CI — including the MCP server.",
        gh: "/blob/main/docs/INTEGRATIONS.md",
      },
      {
        name: "DASHBOARD.md",
        desc: "Reading and driving the self-hosted dashboard: reports, hotspots, and the fusion view.",
        gh: "/blob/main/docs/DASHBOARD.md",
      },
    ],
  },
  {
    crumb: "04",
    title: "Project",
    blurb: "The decisions, audits, and plans behind the build — the paper trail.",
    links: [
      {
        name: "Architecture decision records",
        desc: "The full set of ADRs: stack, MIT-forever license, local-first shape, auth posture, and more.",
        gh: "/tree/main/docs/adr",
      },
      {
        name: "AUDIT.md",
        desc: "The security and correctness audit — what was checked and what was found.",
        gh: "/blob/main/docs/AUDIT.md",
      },
      {
        name: "QUALITY-BARS.md",
        desc: "The quality bars every change is held to before it ships.",
        gh: "/blob/main/docs/QUALITY-BARS.md",
      },
      {
        name: "PACKAGING.md",
        desc: "How the package and its pre-built dashboard assets are built and released.",
        gh: "/blob/main/docs/PACKAGING.md",
      },
      {
        name: "ROADMAP-FULL-PRODUCTION.md",
        desc: "The path to a full production release, and what is deliberately deferred.",
        gh: "/blob/main/docs/ROADMAP-FULL-PRODUCTION.md",
      },
    ],
  },
];

function DocCard({ link }: { link: DocLink }) {
  const isInternal = typeof link.to === "string";
  const label = isInternal ? `${link.name} →` : `${link.name} ↗`;
  const className =
    "block h-full rounded-sm border border-line bg-card p-5 transition-colors hover:border-accent/40";
  const inner = (
    <>
      <div className="mb-1 text-sm text-accent">{label}</div>
      <p className="text-[13px] leading-relaxed text-secondary">{link.desc}</p>
    </>
  );

  if (isInternal) {
    return (
      <Link href={link.to as string} className={className}>
        {inner}
      </Link>
    );
  }
  return (
    <a href={`${GITHUB}${link.gh}`} className={className}>
      {inner}
    </a>
  );
}

export default function DocsPage() {
  return (
    <>
      <PageHeader
        crumb="// documentation"
        title={
          <>
            Read the <span className="text-accent">source of truth</span>.
          </>
        }
        sub="Every page here links to the real, in-repo documentation on GitHub — nothing is duplicated or paraphrased. Start with install and self-host, then go as deep as the decision records."
      />
      <main className="mx-auto max-w-5xl space-y-14 px-6 py-14">
        {GROUPS.map((group) => (
          <section key={group.title}>
            <div className="mb-5 flex items-baseline gap-3">
              <span className="text-xs text-accent">{group.crumb}</span>
              <h2 className="text-xs tracking-widest text-mute">/// {group.title}</h2>
            </div>
            <p className="mb-5 max-w-3xl text-sm leading-relaxed text-secondary">{group.blurb}</p>
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {group.links.map((link) => (
                <li key={link.name}>
                  <DocCard link={link} />
                </li>
              ))}
            </ul>
          </section>
        ))}

        <section className="border-t border-line pt-12">
          <div className="rounded-sm border border-accent/30 bg-accent/5 p-6">
            <div className="mb-2 font-bold text-accent">The docs live with the code.</div>
            <p className="mb-4 max-w-2xl text-sm text-secondary">
              These files are versioned in the repository alongside the code they describe, so they
              move in lockstep with it. Read them there, and open an issue if anything is unclear or
              wrong.
            </p>
            <a
              href={GITHUB}
              className="inline-flex items-center gap-2 rounded-sm border border-accent/40 px-4 py-3 text-sm text-accent transition-colors hover:bg-accent/10"
            >
              Browse the repository →
            </a>
          </div>
        </section>
      </main>
    </>
  );
}
