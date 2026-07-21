import type { ReactNode } from "react";
import { Container } from "@/components/ui/container";
import { Eyebrow } from "@/components/ui/container";

export function PageHeader({
  eyebrow,
  title,
  lede,
}: {
  eyebrow: string;
  title: ReactNode;
  lede?: ReactNode;
}) {
  return (
    <header className="border-hairline border-b">
      <Container className="py-14 md:py-20">
        <Eyebrow>{eyebrow}</Eyebrow>
        <h1 className="mt-4 max-w-[20ch] text-[length:var(--text-h1)] leading-[var(--text-h1--line-height)] font-semibold text-balance">
          {title}
        </h1>
        {lede && (
          <p className="text-secondary mt-5 max-w-[68ch] font-body text-body-lg">
            {lede}
          </p>
        )}
      </Container>
    </header>
  );
}
