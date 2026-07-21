import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { DocH2, DocP, IC } from "@/components/ui/doc";
import { ButtonLink } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { ArrowUpRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "CLI Reference",
  description:
    "The MRI command-line reference: init, scan, serve, watch, report, fusion, mcp, demo, and more — matched to the real CLI surface, no aspirational commands.",
  alternates: { canonical: "/docs/cli" },
};

const COMMANDS = [
  ["mri init", "Create the local admin user and database. Idempotent — safe to re-run."],
  ["mri scan <path|url>", "Analyze a local checkout or a remote repo (shallow clone, auto-cleanup)."],
  ["mri serve", `Serve the dashboard + API on 127.0.0.1:${SITE.port} (loopback).`],
  ["mri watch <path>", "Re-scan on change for continuous, local monitoring."],
  ["mri report", "Emit a self-contained HTML report for a scan."],
  ["mri fusion", "Show the AI-provenance fusion view: authorship, decisions, consequences."],
  ["mri mcp", "Start the read-only MCP server (stdio) for agents."],
  ["mri eval", "Run the evaluation harness against the labelled corpus."],
  ["mri demo", "Run a self-contained demo scan with bundled sample data."],
  ["mri backup / restore", "Back up or restore the local database."],
] as const;

export default function CliPage() {
  return (
    <>
      <PageHeader
        eyebrow="docs · cli"
        title="CLI reference."
        lede="Every subcommand below exists in the real CLI. Verbs, never noun-first. Run mri --help for the authoritative, version-matched surface."
      />
      <Section>
        <Container narrow>
          <DocH2>Commands</DocH2>
          <DocP>
            The binary is <IC>mri</IC> (installed from the <IC>{SITE.pkg}</IC>{" "}
            package). Global flags like <IC>--help</IC> and <IC>--version</IC> work
            on every subcommand.
          </DocP>
          <div className="mt-6 overflow-hidden rounded-md border border-[var(--color-hairline)]">
            <table className="w-full border-collapse text-left">
              <caption className="sr-only">MRI CLI commands</caption>
              <tbody>
                {COMMANDS.map(([cmd, desc]) => (
                  <tr
                    key={cmd}
                    className="border-hairline border-b last:border-b-0"
                  >
                    <th
                      scope="row"
                      className="bg-inset text-primary w-[42%] px-4 py-3 align-top font-mono text-mono-sm font-normal"
                    >
                      {cmd}
                    </th>
                    <td className="text-secondary px-4 py-3 align-top font-body text-body-sm leading-relaxed">
                      {desc}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-8">
            <ButtonLink href={`${SITE.github}/blob/main/docs/API.md`} variant="secondary">
              HTTP API reference
              <ArrowUpRightIcon width={16} height={16} />
            </ButtonLink>
          </div>
        </Container>
      </Section>
    </>
  );
}
