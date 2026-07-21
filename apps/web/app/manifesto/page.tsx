import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { ButtonLink } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { ArrowUpRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "Manifesto",
  description:
    "Four convictions behind MRI: facts over magic scores, local-first forever, explain before recommend, and open core forever. Stated plainly, once.",
  alternates: { canonical: "/manifesto" },
};

const PILLARS = [
  {
    n: "01",
    title: "Facts over magic scores.",
    body: "Every number MRI shows traces to a visible, inspectable source: a git commit, a session-log line, a tree-sitter AST node, a complexity measurement. If a claim can't be traced, it doesn't ship. There is no black box, no proprietary model you're asked to trust — the evidence for every score is one click away.",
  },
  {
    n: "02",
    title: "Local-first, forever.",
    body: "The self-hosted product has no telemetry, no phone-home, no required account. Your code, your prompts, and your history never leave your machine. This is not a phase-one trust play that gets walked back once there's a business model — it is the credibility foundation the entire tool stands on, and it is verifiable in the source.",
  },
  {
    n: "03",
    title: "Explain before recommend.",
    body: "MRI surfaces the evidence and lets a human — or an agent, via MCP — draw the conclusion. It does not front-load prescriptive verdicts ahead of the reasoning. It leads with what was found, then what it means, never the reverse. And it says correlates with, never proves: the decision-to-consequence loop is honest about what a measured link can and cannot claim.",
  },
  {
    n: "04",
    title: "Open core, forever.",
    body: "MIT on the entire core is a permanent commitment, not a current pricing tier. Not 'currently free', not 'free during beta' — MIT-forever, stated as settled fact, because it is a settled architectural and licensing decision. Nothing is held back behind a paywall, because there is no paywall.",
  },
] as const;

export default function ManifestoPage() {
  return (
    <>
      <PageHeader
        eyebrow="the manifesto"
        title="Four convictions. Stated once, plainly."
        lede="MRI is a diagnostic instrument pointed at a codebase. An instrument you can't inspect is one you can't trust — so these are not slogans. Each is a decision that shows up in the code."
      />
      <Section>
        <Container narrow>
          <ol className="flex flex-col gap-px overflow-hidden rounded-lg">
            {PILLARS.map((p) => (
              <li
                key={p.n}
                className="border-hairline bg-surface border p-7 md:p-9"
              >
                <div className="flex items-baseline gap-4">
                  <span className="text-accent font-mono text-mono-lg font-semibold">
                    {p.n}
                  </span>
                  <h2 className="text-[length:var(--text-h3)] leading-[var(--text-h3--line-height)] font-semibold">
                    {p.title}
                  </h2>
                </div>
                <p className="text-secondary mt-4 font-body text-body-lg leading-relaxed">
                  {p.body}
                </p>
              </li>
            ))}
          </ol>

          <div className="mt-10 flex flex-wrap gap-3">
            <ButtonLink href={SITE.github}>
              Read the source
              <ArrowUpRightIcon width={16} height={16} />
            </ButtonLink>
            <ButtonLink href="/how-it-works" variant="secondary">
              How it actually works
            </ButtonLink>
          </div>
        </Container>
      </Section>
    </>
  );
}
