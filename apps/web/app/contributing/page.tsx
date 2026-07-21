import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { ButtonLink } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { ArrowUpRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "Contributing",
  description:
    "How to contribute to MRI — fork, branch, build against the quality bars, open a PR. CONTRIBUTING.md in the repository is the source of truth.",
  alternates: { canonical: "/contributing" },
};

const STEPS = [
  {
    cmd: "gh repo fork project-mri/project-mri",
    title: "Fork & clone",
    body: "One Python package. Python 3.10+; pnpm only if you touch the web apps.",
  },
  {
    cmd: "gh issue list --label good-first-issue",
    title: "Pick an issue",
    body: "Grab a labeled starter — or open an issue first and talk it through before building.",
  },
  {
    cmd: "git switch -c fix/your-thing && pytest",
    title: "Branch & build",
    body: "Keep it focused. CI holds the line: ruff clean, types checked, 75% coverage floor.",
  },
  {
    cmd: "gh pr create",
    title: "Open a PR",
    body: "Every product claim is a testable assertion — back your change with a test.",
  },
] as const;

export default function ContributingPage() {
  return (
    <>
      <PageHeader
        eyebrow="contributing"
        title="Build MRI with us."
        lede="MIT-forever and community-run. Four steps from clone to merged — the full guide lives in the repo."
      />
      <Section>
        <Container narrow>
          <ol className="relative flex flex-col">
            {/* the rail */}
            <span
              aria-hidden="true"
              className="border-hairline-strong absolute top-3 bottom-3 left-[7px] border-l border-dashed"
            />
            {STEPS.map((s, i) => (
              <li key={s.title} className="relative flex gap-6 pb-10 pl-8 last:pb-0">
                {/* commit dot */}
                <span
                  aria-hidden="true"
                  className="bg-accent absolute top-1.5 left-0 h-[15px] w-[15px] rounded-full border-4 border-[var(--color-void)]"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                    <span className="text-mute font-mono text-mono-sm">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <h2 className="font-sans text-h3 font-semibold">{s.title}</h2>
                  </div>
                  <p className="text-secondary mt-2 max-w-[58ch] font-body text-body leading-relaxed">
                    {s.body}
                  </p>
                  <code className="bg-inset text-accent border-hairline mt-3 inline-block rounded-sm border px-3 py-1.5 font-mono text-mono-sm break-all">
                    $ {s.cmd}
                  </code>
                </div>
              </li>
            ))}
          </ol>

          <div className="border-hairline mt-12 flex flex-wrap gap-3 border-t pt-8">
            <ButtonLink href={`${SITE.github}/blob/main/CONTRIBUTING.md`}>
              Read CONTRIBUTING.md
              <ArrowUpRightIcon width={16} height={16} />
            </ButtonLink>
            <ButtonLink href={`${SITE.github}/issues`} variant="secondary">
              Good first issues
              <ArrowUpRightIcon width={16} height={16} />
            </ButtonLink>
          </div>
        </Container>
      </Section>
    </>
  );
}
