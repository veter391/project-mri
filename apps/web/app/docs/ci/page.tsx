import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { CodePanel, Prompt, Comment } from "@/components/ui/code-panel";
import { DocH2, DocP, DocList, DocLi, IC } from "@/components/ui/doc";
import { ButtonLink } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { ArrowUpRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "SARIF CI Gate — Fail a PR on Risk",
  description:
    "Gate pull requests on codebase risk with MRI's SARIF export. Wire it into GitHub Actions or GitLab CI, surface findings in the code-scanning UI, and tune the threshold.",
  alternates: { canonical: "/docs/ci" },
};

export default function CiPage() {
  return (
    <>
      <PageHeader
        eyebrow="docs · ci"
        title="Gate a pull request on risk."
        lede="MRI emits SARIF, so its findings show up in the same code-scanning UI as your other tools — and a threshold can fail the build before risky, opaque-provenance code merges."
      />
      <Section>
        <Container narrow>
          <DocH2>Emit SARIF</DocH2>
          <DocP>
            Run a scan in CI and write SARIF. Findings carry authorship
            properties, so an AI-authored high-risk change is visible as such in
            the review.
          </DocP>
          <CodePanel title="ci-scan" copyText="mri scan . --sarif mri.sarif" className="mt-4">
            <Prompt />mri scan . --sarif mri.sarif
          </CodePanel>

          <DocH2>GitHub Actions</DocH2>
          <DocP>
            Upload the SARIF with <IC>github/codeql-action/upload-sarif</IC>, or
            use the composite action from the repo. Fail the job when the risk
            score crosses your threshold.
          </DocP>
          <CodePanel
            title=".github/workflows/mri.yml"
            copyText={"- run: pipx install project-mri && mri scan . --sarif mri.sarif\n- uses: github/codeql-action/upload-sarif@v3\n  with:\n    sarif_file: mri.sarif"}
            className="mt-4"
          >
            <Comment># scan, then surface findings in code scanning</Comment>
            {"\n"}
            <span className="text-secondary">- run:</span> pipx install {SITE.pkg} &amp;&amp; mri scan . --sarif mri.sarif
            {"\n"}
            <span className="text-secondary">- uses:</span> github/codeql-action/upload-sarif@v3
          </CodePanel>

          <DocH2>Tune the gate</DocH2>
          <DocList>
            <DocLi>Fail on a repo- or file-level risk threshold you choose — start lenient, tighten over time.</DocLi>
            <DocLi>A GitLab CI template ships alongside the GitHub action for the same gate.</DocLi>
            <DocLi>Because SARIF is standard, findings sit next to your linters and SAST, not in a silo.</DocLi>
          </DocList>

          <div className="mt-8">
            <ButtonLink href={`${SITE.github}/blob/main/docs/INTEGRATIONS.md`} variant="secondary">
              Full CI + integrations guide
              <ArrowUpRightIcon width={16} height={16} />
            </ButtonLink>
          </div>
        </Container>
      </Section>
    </>
  );
}
