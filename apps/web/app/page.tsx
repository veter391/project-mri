import { SITE } from "@/lib/site";
import { Container, Section, Eyebrow } from "@/components/ui/container";
import { ButtonLink } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CodePanel, Prompt, Comment, Out } from "@/components/ui/code-panel";
import { TerminalWindow } from "@/components/ui/terminal-window";
import { GridField } from "@/components/grid-field";
import { HomeJsonLd } from "@/components/json-ld";
import { AuthorshipSplitBar } from "@/components/viz/authorship-split-bar";
import { DecisionConsequenceStrip } from "@/components/viz/decision-consequence-strip";
import {
  ArrowRightIcon,
  ArrowUpRightIcon,
  GitHubIcon,
  CheckIcon,
} from "@/components/icons";
import { Link } from "@/components/link";

const STAGES = [
  { n: "01", title: "History + structure", body: "Git history × tree-sitter AST — an image, not a guess." },
  { n: "02", title: "Session-log provenance", body: "~/.claude, ~/.cursor → prompt maps to file maps to commit." },
  { n: "03", title: "Authorship-decomposed risk", body: "Each file's risk split into AI vs human shares." },
  { n: "04", title: "Decision provenance", body: "The rationale behind a change, mined and scored." },
  { n: "05", title: "Consequence loop", body: "Did the metric move after? Correlation, guardrailed." },
] as const;

const EVIDENCE = [
  {
    stat: "~13,000",
    unit: "lines",
    body: "An AI-authored pull request the OCaml compiler community declined — over reviewability and provenance, not correctness.",
    source: "OCaml compiler discussion",
    href: "https://github.com/ocaml/ocaml",
  },
  {
    stat: "~81%",
    unit: "more issues",
    body: "Production issues reported by teams shipping opaque-provenance AI-authored code.",
    source: "CloudBees, 2026",
    href: "https://www.cloudbees.com/",
  },
] as const;

const GUARANTEES = [
  "MIT-forever — no open-core split, no paid tier",
  "Zero telemetry — no account, no phone-home",
  "Self-hostable — your code never leaves your machine",
  "Explainable — every score traces to its evidence",
] as const;

export default function HomePage() {
  return (
    <>
      <HomeJsonLd />
      <GridField />

      {/* ---- Hero ---- */}
      <Section className="pt-12 pb-12 md:pt-16 md:pb-16">
        <Container>
            <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_0.95fr]">
              <div className="min-w-0">
                <p className="text-mute font-mono text-mono-sm">
                  <span className="text-accent">$</span> mri --version{" "}
                  <span className="text-secondary">
                    · {SITE.pkg} {SITE.version} · local-first · MIT
                  </span>
                  <span className="mri-caret ml-1.5 opacity-80" />
                </p>
                <div className="mt-5 flex flex-wrap items-center gap-2">
                  <Badge tone="accent">Local-first</Badge>
                  <Badge tone="neutral">MIT-forever</Badge>
                  <Badge tone="neutral">Zero telemetry</Badge>
                </div>
                <h1 className="mt-5 text-[length:var(--text-display)] leading-[var(--text-display--line-height)] font-semibold text-balance">
                  MRI reads what&apos;s actually in your codebase — and{" "}
                  <span className="text-accent">who actually wrote it</span>.
                </h1>
                <p className="text-secondary mt-6 max-w-[52ch] font-body text-body-lg text-pretty">
                  Session-log AI provenance, authorship-decomposed risk, and a
                  decision-to-consequence loop — all on your machine, all
                  explainable, all MIT-forever.
                </p>
                <div className="mt-8 flex flex-wrap items-center gap-3">
                  <ButtonLink href="/demo" size="lg">
                    Try the live demo
                    <ArrowRightIcon width={18} height={18} />
                  </ButtonLink>
                  <ButtonLink href={SITE.github} variant="secondary" size="lg">
                    <GitHubIcon width={18} height={18} />
                    View on GitHub
                  </ButtonLink>
                </div>
                <p className="text-mute mt-5 font-mono text-mono-sm">
                  <span className="text-accent">$</span> pip install {SITE.pkg}
                </p>
              </div>

              <CodePanel
                title="mri scan ."
                meta="project-mri · own repo"
                copyText="mri scan ."
                className="shadow-[var(--elevation-2)]"
              >
                <Prompt />mri scan .{"\n\n"}
                <Comment># git history</Comment>
                {"\n"}  parsed 4,812 commits · 38 authors{"\n"}
                <Comment># tree-sitter</Comment>
                {"\n"}  270 files · 6 languages · 18,452 symbols{"\n"}
                <Comment># session logs</Comment>
                {"\n"}  ~/.claude · mapped prompts → files → commits{"\n"}
                <Comment># risk score</Comment>
                {"\n"}  <span className="text-risk-high">60.0</span> / 100 · measured{"\n"}
                <Comment># report</Comment>
                {"\n"}  ~/.cache/project-mri/reports/…html{"\n\n"}
                <Out>✓ done in 2.5s · 0 telemetry events</Out>
              </CodePanel>
            </div>
        </Container>
      </Section>

      {/* ---- Problem, with evidence (asymmetric bento) ---- */}
      <Section className="py-14 md:py-20">
        <Container>
            <div className="grid gap-5 lg:grid-cols-12 lg:items-stretch">
              {/* lead — the named problem */}
              <div className="border-hairline bg-surface flex flex-col rounded-md border p-7 md:p-9 lg:col-span-6">
                <Eyebrow>the problem</Eyebrow>
                <h2 className="mt-4 text-[length:var(--text-h2)] leading-[var(--text-h2--line-height)] font-semibold text-balance">
                  Teams are shipping code they can&apos;t explain.
                </h2>
                <p className="text-secondary mt-4 font-body text-body-lg text-pretty">
                  The demand has a name. Addy Osmani calls it{" "}
                  <span className="text-primary">comprehension debt</span>: code
                  that ships and runs, but that no one on the team understands
                  well enough to safely change.
                </p>
                <a
                  href="https://addyo.substack.com/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-mute hover:text-primary mt-auto inline-flex w-fit items-center gap-1 pt-6 font-mono text-mono-sm transition-colors"
                >
                  Term coined by Addy Osmani
                  <ArrowUpRightIcon width={13} height={13} />
                </a>
              </div>

              {/* two stacked evidence stats */}
              <div className="flex flex-col gap-5 lg:col-span-6">
                {EVIDENCE.map((e) => (
                  <a
                    key={e.source}
                    href={e.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group border-hairline bg-surface hover:border-hairline-strong flex flex-1 flex-col justify-between rounded-md border p-6 transition-colors"
                  >
                    <div className="flex items-baseline gap-2">
                      <span className="text-accent font-sans text-[length:var(--text-h1)] leading-none font-semibold tabular-nums">
                        {e.stat}
                      </span>
                      <span className="text-mute font-mono text-mono-sm">
                        {e.unit}
                      </span>
                    </div>
                    <p className="text-secondary mt-3 font-body text-body-sm leading-relaxed text-pretty">
                      {e.body}
                    </p>
                    <span className="text-mute group-hover:text-primary mt-4 inline-flex items-center gap-1 font-mono text-mono-sm transition-colors">
                      {e.source}
                      <ArrowUpRightIcon width={13} height={13} />
                    </span>
                  </a>
                ))}
              </div>
            </div>
        </Container>
      </Section>

      {/* ---- The pipeline (framed as an instrument readout) ---- */}
      <Section className="py-14 md:py-20">
        <Container>
            <div className="mb-8 flex flex-col gap-3">
              <Eyebrow>what closes the loop</Eyebrow>
              <h2 className="text-[length:var(--text-h2)] leading-[var(--text-h2--line-height)] font-semibold text-balance">
                Five stages, one complete loop.
              </h2>
              <p className="text-secondary max-w-[64ch] font-body text-body-lg text-pretty">
                Individually, most of these have a rival. Together — as a
                complete, trustworthy, free, self-hostable loop — MRI stands
                alone.
              </p>
            </div>

            <TerminalWindow
              title="mri://pipeline"
              meta="git+ast → provenance → risk → decision → consequence"
              bodyClassName="p-4 md:p-5"
            >
              <ol className="flex flex-col gap-3 lg:flex-row lg:items-stretch">
                {STAGES.map((s, i) => (
                  <li key={s.n} className="contents">
                    <Link
                      href="/how-it-works"
                      className="group border-hairline bg-inset hover:border-accent/40 flex flex-1 flex-col rounded-md border p-4 transition-colors"
                    >
                      <span className="text-accent font-mono text-mono-sm font-medium">
                        {s.n}
                      </span>
                      <h3 className="mt-2 font-sans text-body-sm font-semibold">
                        {s.title}
                      </h3>
                      <p className="text-mute mt-1.5 font-body text-mono-sm leading-relaxed">
                        {s.body}
                      </p>
                    </Link>
                    {i < STAGES.length - 1 && (
                      <span
                        aria-hidden="true"
                        className="text-hairline-strong flex items-center justify-center self-center font-mono lg:px-0.5"
                      >
                        <span className="lg:hidden">↓</span>
                        <span className="hidden lg:inline">→</span>
                      </span>
                    )}
                  </li>
                ))}
              </ol>
            </TerminalWindow>

            <p className="text-mute mt-4 font-mono text-mono-sm">
              → surfaced to humans (dashboard · HTML report · CLI · SARIF gate)
              and agents (MCP server).
            </p>
        </Container>
      </Section>

      {/* ---- Demo teaser ---- */}
      <Section className="py-14 md:py-20">
        <Container>
            <div className="grid items-center gap-10 lg:grid-cols-2">
              <div className="min-w-0">
                <Eyebrow>see it work</Eyebrow>
                <h2 className="mt-3 text-[length:var(--text-h2)] leading-[var(--text-h2--line-height)] font-semibold text-balance">
                  Authorship-decomposed risk, and a decision you can trace.
                </h2>
                <p className="text-secondary mt-4 max-w-[52ch] font-body text-body-lg text-pretty">
                  Every panel links to the exact commit, line, or AST node behind
                  it. Nothing here asks for trust — only inspection.
                </p>
                <div className="mt-6">
                  <ButtonLink href="/demo" variant="secondary">
                    Explore the live demo
                    <ArrowRightIcon width={16} height={16} />
                  </ButtonLink>
                </div>
              </div>

              <TerminalWindow
                title="mri://fusion · services/auth/session.py"
                meta="illustrative"
                tone="surface"
                bodyClassName="flex flex-col gap-5 p-5"
              >
                <div>
                  <p className="text-mute mb-2 font-mono text-mono-sm">
                    authorship share
                  </p>
                  <AuthorshipSplitBar shares={{ human: 52, ai: 41, unattributed: 7 }} />
                </div>
                <DecisionConsequenceStrip
                  decision="Split the monolith auth module into a session service."
                  consequence="Coupling on that path fell over the next 30 days."
                  direction="improved"
                  confidence="MED"
                />
              </TerminalWindow>
            </div>
        </Container>
      </Section>

      {/* ---- Open source, forever ---- */}
      <Section className="py-14 md:py-24">
        <Container>
            <div className="grid items-stretch gap-5 lg:grid-cols-[1.25fr_1fr]">
              <div className="border-hairline bg-raised flex flex-col justify-center rounded-md border p-8 md:p-10">
                <Eyebrow>open source, forever</Eyebrow>
                <h2 className="mt-4 text-[length:var(--text-h2)] leading-[var(--text-h2--line-height)] font-semibold text-balance">
                  A tool that reads your prompts must be inspectable — and
                  un-revocable.
                </h2>
                <p className="text-secondary mt-4 max-w-[54ch] font-body text-body-lg text-pretty">
                  MIT-licensed on the whole core, forever. Zero telemetry, proven
                  by a build-failing egress test. Fully self-hostable. Nothing
                  held back behind a paywall — because there is no paywall.
                </p>
                <div className="mt-7 flex flex-wrap gap-3">
                  <ButtonLink href={SITE.license}>
                    Read the license
                    <ArrowUpRightIcon width={16} height={16} />
                  </ButtonLink>
                  <ButtonLink href="/manifesto" variant="ghost">
                    The manifesto
                    <ArrowRightIcon width={16} height={16} />
                  </ButtonLink>
                </div>
              </div>

              <TerminalWindow title="guarantees.txt" meta="verifiable" tone="surface">
                <ul className="flex flex-col gap-3">
                  {GUARANTEES.map((line) => (
                    <li
                      key={line}
                      className="text-secondary flex items-start gap-3 font-body text-body-sm leading-relaxed"
                    >
                      <CheckIcon
                        width={16}
                        height={16}
                        className="text-accent mt-0.5 shrink-0"
                      />
                      {line}
                    </li>
                  ))}
                </ul>
              </TerminalWindow>
            </div>
        </Container>
      </Section>
    </>
  );
}
