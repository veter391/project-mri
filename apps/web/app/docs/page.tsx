import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { TerminalWindow } from "@/components/ui/terminal-window";
import { Link } from "@/components/link";
import { SITE } from "@/lib/site";
import { ArrowRightIcon, ArrowUpRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "Docs — Install, Run, and Understand MRI",
  description:
    "The MRI documentation index: quickstart, CLI reference, MCP server, SARIF CI gate, session-log setup, self-hosting, and architecture. Every page links to the real in-repo source.",
  alternates: { canonical: "/docs" },
};

const GH = SITE.github;

type DocRow = { name: string; desc: string; href: string };

const GROUPS: { dir: string; note: string; rows: DocRow[] }[] = [
  {
    dir: "~/docs/getting-started",
    note: "install → scan → report",
    rows: [
      { name: "quickstart.md", desc: "Install, mri scan ., first report — five minutes.", href: "/docs/quickstart" },
      { name: "self-hosting.md", desc: "The full dashboard + backend on your machine.", href: "/docs/self-hosting" },
      { name: "CONFIG.md", desc: "Every .mri.yml key, its default, what it changes.", href: `${GH}/blob/main/docs/CONFIG.md` },
    ],
  },
  {
    dir: "~/docs/understanding",
    note: "how the numbers happen",
    rows: [
      { name: "METHODOLOGY.md", desc: "How history + structure become explainable scores.", href: `${GH}/blob/main/docs/METHODOLOGY.md` },
      { name: "TRUST.md", desc: "Each guarantee, mapped to the test that proves it.", href: `${GH}/blob/main/docs/TRUST.md` },
      { name: "how-it-works", desc: "The five-stage loop, with real module paths.", href: "/how-it-works" },
    ],
  },
  {
    dir: "~/docs/reference",
    note: "the surfaces you build against",
    rows: [
      { name: "cli.md", desc: "Every mri subcommand — no aspirational commands.", href: "/docs/cli" },
      { name: "mcp.md", desc: "The agent-facing MCP server, and how to wire it.", href: "/docs/mcp" },
      { name: "ci.md", desc: "Gate a pull request on risk with SARIF.", href: "/docs/ci" },
      { name: "session-log-setup.md", desc: "Point MRI at ~/.claude and ~/.cursor.", href: "/docs/session-log-setup" },
    ],
  },
  {
    dir: "~/docs/project",
    note: "decisions and architecture",
    rows: [
      { name: "architecture.md", desc: "The module map, for contributors.", href: "/docs/architecture" },
      { name: "adr/", desc: "Every architecture decision record, in the open.", href: `${GH}/tree/main/docs/adr` },
      { name: "AUDIT.md", desc: "The security audit — checked, and what was found.", href: `${GH}/blob/main/docs/AUDIT.md` },
    ],
  },
];

function Row({ row }: { row: DocRow }) {
  const external = row.href.startsWith("http");
  const inner = (
    <>
      <span className="text-mute hidden shrink-0 font-mono text-mono-sm sm:inline">
        -rw-r--r--
      </span>
      <span className="text-accent shrink-0 font-mono text-mono-sm group-hover:underline">
        {row.name}
      </span>
      <span className="text-secondary min-w-0 flex-1 truncate font-body text-body-sm">
        {row.desc}
      </span>
      {external ? (
        <ArrowUpRightIcon width={14} height={14} className="text-mute shrink-0" />
      ) : (
        <ArrowRightIcon
          width={14}
          height={14}
          className="text-mute shrink-0 transition-transform duration-100 group-hover:translate-x-0.5"
        />
      )}
    </>
  );
  const cls =
    "group flex items-center gap-3 px-5 py-3 transition-colors hover:bg-[var(--accent-wash)]";
  return external ? (
    <a href={row.href} target="_blank" rel="noopener noreferrer" className={cls}>
      {inner}
    </a>
  ) : (
    <Link href={row.href} className={cls}>
      {inner}
    </Link>
  );
}

export default function DocsPage() {
  return (
    <>
      <PageHeader
        eyebrow="documentation"
        title="Read the source of truth."
        lede="Everything links to the real, in-repo docs — nothing paraphrased, nothing duplicated. Start at the quickstart; go as deep as the decision records."
      />
      <Section>
        <Container>
          <div className="grid gap-6 lg:grid-cols-2">
            {GROUPS.map((g) => (
              <TerminalWindow
                key={g.dir}
                title={g.dir}
                meta={g.note}
                bodyClassName="p-0"
              >
                <div className="divide-y divide-[var(--color-hairline)]">
                  {g.rows.map((row) => (
                    <Row key={row.name} row={row} />
                  ))}
                </div>
              </TerminalWindow>
            ))}
          </div>
          <p className="text-mute mt-6 font-mono text-mono-sm">
            $ ls ~/docs · 13 entries · versioned with the code they describe
          </p>
        </Container>
      </Section>
    </>
  );
}
