import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { CodePanel, Prompt, Comment } from "@/components/ui/code-panel";
import { DocH2, DocP, DocList, DocLi, IC, DocNote } from "@/components/ui/doc";
import { ButtonLink } from "@/components/ui/button";
import { ArrowRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "Session-log Setup — AI Provenance from Your Own Logs",
  description:
    "Point MRI at your local ~/.claude and ~/.cursor session logs to map prompt → file → commit. The data never leaves your machine; session content is off by default.",
  alternates: { canonical: "/docs/session-log-setup" },
};

export default function SessionLogSetupPage() {
  return (
    <>
      <PageHeader
        eyebrow="docs · session-log setup"
        title="Provenance from the logs you already have."
        lede="MRI reads the AI-session logs already on your machine to map which prompt produced which lines. This is what separates real provenance from a git-metadata guess."
      />
      <Section>
        <Container narrow>
          <DocH2>Point MRI at your session logs</DocH2>
          <DocP>
            MRI reads local session directories — <IC>~/.claude</IC> and{" "}
            <IC>~/.cursor</IC> — and correlates each session to the earliest
            commit at or after the files were touched. Where{" "}
            <IC>Agent Trace</IC> or <IC>git-ai</IC> have written provenance as
            git-notes, MRI consumes those too.
          </DocP>
          <CodePanel
            title="fusion"
            copyText="mri scan . --sessions ~/.claude\nmri fusion"
            className="mt-4"
          >
            <Comment># include local session logs in the scan, then view fusion</Comment>
            {"\n"}
            <Prompt />mri scan . --sessions ~/.claude
            {"\n"}
            <Prompt />mri fusion
          </CodePanel>

          <DocH2>What it does — and does not do</DocH2>
          <DocList>
            <DocLi>Maps prompt → file → commit, then decomposes each file&apos;s risk into AI vs human shares.</DocLi>
            <DocLi>Reports lines it cannot attribute as unattributed — never as human-written.</DocLi>
            <DocLi>Does not call any cloud API to reconstruct sessions that were never logged. It reads what exists.</DocLi>
          </DocList>

          <DocH2>Privacy</DocH2>
          <DocNote>
            Session <strong>content</strong> is off by default
            (<IC>store_content=False</IC>), enforced at the database layer — MRI
            stores the metadata it needs for attribution, not your prompt text,
            unless you explicitly enable it. In self-hosted mode this data never
            leaves your machine.
          </DocNote>

          <div className="mt-8">
            <ButtonLink href="/how-it-works">
              How provenance actually works
              <ArrowRightIcon width={16} height={16} />
            </ButtonLink>
          </div>
        </Container>
      </Section>
    </>
  );
}
