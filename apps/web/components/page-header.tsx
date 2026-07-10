import type { ReactNode } from "react";

export function PageHeader({
  crumb,
  title,
  sub,
}: {
  crumb: string;
  title: ReactNode;
  sub?: string;
}) {
  return (
    <header className="border-b border-line py-16">
      <div className="mx-auto max-w-5xl px-6">
        <p className="mb-4 text-xs tracking-widest text-accent">{crumb}</p>
        <h1 className="max-w-3xl text-3xl font-bold leading-tight sm:text-5xl">{title}</h1>
        {sub ? <p className="mt-5 max-w-2xl text-base leading-relaxed text-secondary">{sub}</p> : null}
      </div>
    </header>
  );
}
