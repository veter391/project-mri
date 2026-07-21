import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/page-header";
import { Container, Section } from "@/components/ui/container";
import { Card } from "@/components/ui/card";
import { ButtonLink } from "@/components/ui/button";
import { SITE } from "@/lib/site";
import { ArrowUpRightIcon } from "@/components/icons";

export const metadata: Metadata = {
  title: "Contributing",
  description:
    "How to contribute to MRI — the source of truth is CONTRIBUTING.md in the repository. Fork, branch, and open a PR; good-first-issues are labeled on GitHub.",
  alternates: { canonical: "/contributing" },
};

const STEPS = [
  ["Fork & clone", "Fork the repository, clone it, and install with the documented dev setup. Python 3.10+; pnpm only for the web apps."],
  ["Pick an issue", "Start with a good-first-issue on GitHub, or open one to discuss a change before you build it."],
  ["Branch & build", "Work on a branch. Keep changes focused; the CI enforces ruff, type checks, and the 75% coverage floor."],
  ["Open a PR", "Open a pull request against main. Every claim about the product is a testable assertion — back changes with tests."],
] as const;

export default function ContributingPage() {
  return (
    <>
      <PageHeader
        eyebrow="contributing"
        title="Build MRI with us."
        lede="MRI is MIT-forever and community-driven. The authoritative contribution guide lives in the repository — this is the short version to get you oriented."
      />
      <Section>
        <Container narrow>
          <ol className="grid gap-3 sm:grid-cols-2">
            {STEPS.map(([title, body], i) => (
              <li key={title}>
                <Card className="h-full">
                  <span className="text-accent font-mono text-mono-sm">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <h2 className="mt-2 font-sans text-body font-semibold">{title}</h2>
                  <p className="text-secondary mt-2 font-body text-body-sm leading-relaxed">
                    {body}
                  </p>
                </Card>
              </li>
            ))}
          </ol>
          <div className="mt-8 flex flex-wrap gap-3">
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
