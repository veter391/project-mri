import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { DocH2, DocP, IC } from "@/components/ui/doc";
import { ButtonLink } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { ArrowUpRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "Architecture — The MRI Module Map",
  description:
    "How MRI fits together: analyzers, the session-log ingest and fusion engine, the database, the HTTP API, the CLI, and the MCP surface — aimed at contributors.",
  alternates: { canonical: "/docs/architecture" },
};

const MODULES = [
  ["analyzers/", "Six analyzers (git history, complexity, tech debt, coupling, architecture, dependencies), each emitting a 0–100 score with a contributor ledger."],
  ["session-log ingest", "Reads ~/.claude / ~/.cursor and consumes Agent Trace / git-ai git-notes; correlates sessions to commits."],
  ["fusion engine", "Decomposes risk by authorship, mines decisions, and correlates them to later measured consequences — guardrailed."],
  ["db", "Local database with schema migrations; content-retention triggers enforce session-content-off-by-default."],
  ["api", "The HTTP API the dashboard is built on; loopback-first, fail-closed when exposed without auth."],
  ["cli", "The mri command surface — scan, serve, watch, fusion, mcp, and more."],
  ["mcp", "A read-only MCP server (stdio) exposing the intelligence model to agents."],
] as const;

export default function ArchitecturePage() {
  return (
    <>
      <PageHeader
        eyebrow="docs · architecture"
        title="The module map."
        lede="MRI is a pipeline: raw history and structure in, an explainable, authorship-decomposed model out, surfaced to humans and agents. Here is how the pieces fit — for contributors."
      />
      <Section>
        <Container narrow>
          <DocH2>Modules</DocH2>
          <DocP>
            The package lives under <IC>backend/mri/</IC>. Each module below owns
            one responsibility; the docs link to the real source.
          </DocP>
          <div className="mt-6 overflow-hidden rounded-md border border-[var(--color-hairline)]">
            <table className="w-full border-collapse text-left">
              <caption className="sr-only">MRI modules</caption>
              <tbody>
                {MODULES.map(([mod, desc]) => (
                  <tr key={mod} className="border-hairline border-b last:border-b-0">
                    <th
                      scope="row"
                      className="bg-inset text-primary w-[34%] px-4 py-3 align-top font-mono text-mono-sm font-normal"
                    >
                      {mod}
                    </th>
                    <td className="text-secondary px-4 py-3 align-top font-body text-body-sm leading-relaxed">
                      {desc}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <DocH2>Two apps, one brand</DocH2>
          <DocP>
            The self-hosted dashboard (served by the backend) and this public
            marketing site are deliberately separate apps. The dashboard has zero
            telemetry and no external calls by design; keeping the two apart makes
            that guarantee trivially auditable — grep the dashboard&apos;s shipped
            JS and find no analytics, full stop.
          </DocP>

          <div className="mt-8">
            <ButtonLink href={`${SITE.github}/tree/main/docs/adr`} variant="secondary">
              Architecture decision records
              <ArrowUpRightIcon width={16} height={16} />
            </ButtonLink>
          </div>
        </Container>
      </Section>
    </>
  );
}
