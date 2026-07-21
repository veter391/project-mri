import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { CodePanel, Prompt, Comment, Out } from "@/components/ui/code-panel";
import { DocH2, DocP, DocList, DocLi, IC } from "@/components/ui/doc";
import { ButtonLink } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { ArrowRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "Quickstart — Install and Run MRI in 5 Minutes",
  description:
    "Install MRI with pip or pipx, run mri scan . on a repository, and open your first self-contained report — local-first, in about five minutes.",
  alternates: { canonical: "/docs/quickstart" },
};

export default function QuickstartPage() {
  return (
    <>
      <PageHeader
        eyebrow="docs · quickstart"
        title="Install and run MRI in five minutes."
        lede="One Python package. No account, no cloud, no telemetry. The dashboard ships pre-built, so there is no Node runtime to install."
      />
      <Section>
        <Container narrow>
          <DocH2>1 · Install</DocH2>
          <DocP>
            MRI is a single Python package (<IC>project-mri</IC>) exposing an{" "}
            <IC>mri</IC> binary. Python 3.10+ is required.
          </DocP>
          <CodePanel title="install" copyText={`pipx install ${SITE.pkg}\nmri --version`} className="mt-4">
            <Comment># pipx keeps it isolated; pip and uvx work too</Comment>
            {"\n"}
            <Prompt />pipx install {SITE.pkg}
            {"\n"}
            <Prompt />mri --version
            {"\n"}
            <Out>project-mri {SITE.version}</Out>
          </CodePanel>

          <DocH2>2 · Scan a repository</DocH2>
          <DocP>
            Point <IC>mri scan</IC> at a local checkout. Results are written to
            your local cache — nothing leaves your machine.
          </DocP>
          <CodePanel title="scan" copyText="mri scan ." className="mt-4">
            <Prompt />mri scan .{"\n\n"}
            <Comment># or a remote repo — shallow-cloned into a sandbox, cleaned up after</Comment>
            {"\n"}
            <Prompt />mri scan https://github.com/yourorg/yourrepo.git
          </CodePanel>

          <DocH2>3 · Open the report, or the dashboard</DocH2>
          <DocP>
            Every scan produces a self-contained HTML report you can archive or
            share. Or run the local dashboard on <IC>127.0.0.1:{SITE.port}</IC>.
          </DocP>
          <CodePanel title="serve" copyText="mri serve" className="mt-4">
            <Prompt />mri serve
            {"\n"}
            <Comment># → http://localhost:{SITE.port}/dashboard/</Comment>
          </CodePanel>

          <DocH2>What you get</DocH2>
          <DocList>
            <DocLi>A 0–100 risk score per file and repo, each decomposable into its contributing signals.</DocLi>
            <DocLi>Authorship shares (human / AI / unattributed) where session logs are present.</DocLi>
            <DocLi>Hotspots, bus factor, coupling and complexity — every number traceable to its source.</DocLi>
            <DocLi>A self-contained HTML report, SARIF for CI, and an MCP surface for agents.</DocLi>
          </DocList>

          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href="/docs/session-log-setup">
              Set up session-log provenance
              <ArrowRightIcon width={16} height={16} />
            </ButtonLink>
            <ButtonLink href="/docs/cli" variant="secondary">
              CLI reference
            </ButtonLink>
          </div>
        </Container>
      </Section>
    </>
  );
}
