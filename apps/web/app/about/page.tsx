import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { ButtonLink } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { ArrowRightIcon, ArrowUpRightIcon } from "@/components/icons";
import { Watermark } from "@/components/ui/watermark";

export const metadata: Metadata = {
  title: "About",
  description:
    "Why MRI exists: teams are accumulating code nobody can safely change. MRI is the local-first, MIT-forever answer — real provenance, explainable risk, zero telemetry.",
  alternates: { canonical: "/about" },
};

const STATS = [
  ["270", "files scanned on MRI's own repo"],
  ["2.5s", "for that full scan, measured"],
  ["0", "telemetry events — build-tested"],
] as const;

export default function AboutPage() {
  return (
    <>
      <PageHeader
        eyebrow="about"
        title="Why MRI exists."
        lede="Every engineer eventually inherits a codebase with no context. Every team eventually loses the 'why' behind a decision. AI made both problems sharper — and gave them a name."
      />

      {/* stat strip — eats its own dog food */}
      <div className="border-hairline border-b">
        <Container>
          <dl className="grid divide-y divide-[var(--color-hairline)] sm:grid-cols-3 sm:divide-x sm:divide-y-0">
            {STATS.map(([num, label]) => (
              <div key={label} className="flex flex-col gap-1 px-2 py-6 sm:px-8 sm:first:pl-2 md:py-8">
                <dt className="sr-only">{label}</dt>
                <dd className="text-accent font-mono text-[2.2rem] leading-none font-bold tabular-nums">
                  {num}
                </dd>
                <dd className="text-mute font-body text-body-sm">{label}</dd>
              </div>
            ))}
          </dl>
        </Container>
      </div>

      <Section>
        <Container narrow>
          <div className="text-secondary flex flex-col gap-5 font-body text-body-lg leading-relaxed">
            <p>
              Teams ship code faster than they understand it. Addy Osmani gave
              the result a name — <span className="text-primary">comprehension debt</span>:
              code that runs, but that nobody can safely change. It&apos;s not
              theoretical. The OCaml community turned away a ~13,000-line
              AI-authored pull request — not because it was wrong, but because
              nobody could review it. And 2026 research tied opaque AI code to
              far more production incidents.
            </p>
            <p>
              MRI is the answer we wanted to exist: read the git history, the
              AST, and the AI-session logs already on your machine — then show
              which code is AI-authored, why it&apos;s risky, and whether past
              decisions actually seemed to help. Every number traces to its
              evidence. Nothing leaves your machine.
            </p>
          </div>
        </Container>
      </Section>

      {/* pull-quote banner */}
      <div className="border-hairline bg-raised relative overflow-hidden border-y">
        <Watermark text=">_" className="-top-6 left-4 h-40 text-accent md:h-52" />
        <Container className="py-14 md:py-20">
          <blockquote className="relative">
            <p className="max-w-[24ch] font-sans text-[length:var(--text-h1)] leading-[1.15] font-semibold text-balance">
              The tooling for understanding a codebase should be{" "}
              <span className="text-accent">local, free, and open</span> —
              forever.
            </p>
            <footer className="text-mute mt-5 font-mono text-mono-sm">
              — the one conviction MRI is built on
            </footer>
          </blockquote>
        </Container>
      </div>

      <Section>
        <Container narrow>
          <p className="text-secondary font-body text-body-lg leading-relaxed">
            That&apos;s why it&apos;s MIT on the whole core, forever, with zero
            telemetry. A tool that reads your prompts and your source has to be
            inspectable and un-revocable to deserve your trust. Not a launch
            phase — the foundation.
          </p>
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
