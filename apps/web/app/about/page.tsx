import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { ButtonLink } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { ArrowRightIcon, ArrowUpRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "About",
  description:
    "MRI exists because teams are accumulating code they can't explain, review, or safely change faster than they can understand it. A local-first, MIT-forever response to comprehension debt.",
  alternates: { canonical: "/about" },
};

export default function AboutPage() {
  return (
    <>
      <PageHeader
        eyebrow="about"
        title="Why MRI exists."
        lede="Every engineer eventually inherits a codebase with no context. Every team eventually loses the 'why' behind a decision. AI-assisted development made both problems sharper — and gave them a name."
      />
      <Section>
        <Container narrow>
          <div className="flex flex-col gap-5 font-body text-body-lg leading-relaxed text-secondary">
            <p>
              Teams are shipping code faster than they can understand it. Addy
              Osmani calls the result <span className="text-primary">comprehension debt</span>:
              code that runs but that no one can safely change. It is not a
              hypothetical — a flagship open-source project declined a
              ~13,000-line AI-authored pull request over reviewability, not
              correctness, and 2026 research tied opaque-provenance AI code to
              markedly more production issues.
            </p>
            <p>
              MRI is a response to that, built on one conviction:{" "}
              <span className="text-primary">the tooling for understanding a codebase should be local, free, and open — forever.</span>{" "}
              It reads what is actually there — the git history, the AST, and the
              AI-session logs already on your machine — and shows which code is
              AI-authored, why it is risky, and whether past decisions actually
              seemed to help. Every number traces to its evidence. Nothing is
              sent anywhere.
            </p>
            <p>
              It is MIT-licensed on the whole core, forever, with zero telemetry,
              because a tool that reads your prompts and your source has to be
              inspectable and un-revocable to deserve adoption. That is not a
              phase; it is the foundation.
            </p>
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href="/manifesto">
              The manifesto
              <ArrowRightIcon width={16} height={16} />
            </ButtonLink>
            <ButtonLink href={SITE.github} variant="secondary">
              <ArrowUpRightIcon width={16} height={16} />
              The repository
            </ButtonLink>
          </div>
        </Container>
      </Section>
    </>
  );
}
