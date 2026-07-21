import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { CodePanel, Prompt, Comment } from "@/components/ui/code-panel";
import { DocH2, DocP, DocList, DocLi, IC } from "@/components/ui/doc";
import { ButtonLink } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { ArrowUpRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "MCP Server — Agent-Native Codebase Risk",
  description:
    "MRI ships a read-only MCP server over stdio so agents like Claude Code and Cursor can query risk, authorship, and decisions before touching a file. Concrete tools, concrete setup.",
  alternates: { canonical: "/docs/mcp" },
};

export default function McpPage() {
  return (
    <>
      <PageHeader
        eyebrow="docs · mcp"
        title="Agent-native, over MCP."
        lede="MRI exposes a read-only Model Context Protocol server so an agent can ask 'what's the risk decomposition of this file before I touch it' — and get a real, sourced answer."
      />
      <Section>
        <Container narrow>
          <DocH2>What it is</DocH2>
          <DocP>
            The MCP server runs locally over <IC>stdio</IC> (per ADR-014) and is
            read-only — it answers questions about the intelligence model MRI has
            already built, and never mutates your repo. It ships as an optional{" "}
            <IC>[mcp]</IC> extra.
          </DocP>

          <DocH2>Start it</DocH2>
          <CodePanel title="mcp" copyText={`pip install "${SITE.pkg}[mcp]"\nmri mcp`} className="mt-4">
            <Comment># install the optional MCP extra, then start the stdio server</Comment>
            {"\n"}
            <Prompt />pip install &quot;{SITE.pkg}[mcp]&quot;
            {"\n"}
            <Prompt />mri mcp
          </CodePanel>

          <DocH2>Point an agent at it</DocH2>
          <DocP>
            Register <IC>mri mcp</IC> as an MCP server in your agent&apos;s config
            (Claude Code, Cursor, or any MCP-capable client). The tools become
            available to the model the way any other MCP tool does.
          </DocP>
          <DocList>
            <DocLi>Query a file&apos;s risk decomposition and its contributing signals.</DocLi>
            <DocLi>Read authorship shares for a file or path (human / AI / unattributed).</DocLi>
            <DocLi>Inspect decisions and their correlated consequences, with confidence.</DocLi>
          </DocList>

          <div className="mt-8">
            <ButtonLink href={`${SITE.github}/blob/main/docs/INTEGRATIONS.md`}>
              Full MCP + integrations guide
              <ArrowUpRightIcon width={16} height={16} />
            </ButtonLink>
          </div>
        </Container>
      </Section>
    </>
  );
}
