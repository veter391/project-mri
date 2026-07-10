import type { Metadata } from "next";
import { PageHeader } from "@/components/page-header";

const GITHUB = "https://github.com/veter391/project-mri";

export const metadata: Metadata = {
  title: "About · project-mri",
  description: "What project-mri is, its license, and how to contribute.",
};

export default function AboutPage() {
  return (
    <>
      <PageHeader
        crumb="// about"
        title={<>Understand your project. Before it understands you.</>}
        sub="project-mri is a local-first, privacy-friendly tool that performs a deep diagnostic of a codebase and its history — the way an MRI scans a body."
      />
      <main className="mx-auto max-w-5xl space-y-10 px-6 py-14">
        <section>
          <h2 className="mb-3 text-xs tracking-widest text-mute">/// why it exists</h2>
          <p className="max-w-3xl text-sm leading-relaxed text-secondary">
            Modern development — especially with AI coding assistants — makes codebases grow
            faster than any human can understand them. Architectural decisions get lost, debt
            accumulates invisibly, and onboarding takes too long. project-mri turns a repository
            into an explainable, queryable model of its architecture, history, and health — so
            you can see the risk before it bites.
          </p>
        </section>

        <section id="license">
          <h2 className="mb-3 text-xs tracking-widest text-mute">/// license</h2>
          <p className="max-w-3xl text-sm leading-relaxed text-secondary">
            MIT. The full experience is free, forever, for any use. The analyzers, scoring,
            and reports are open source — fork it, audit it, ship it inside your company.
          </p>
        </section>

        <section>
          <h2 className="mb-3 text-xs tracking-widest text-mute">/// contribute</h2>
          <p className="max-w-3xl text-sm leading-relaxed text-secondary">
            Contributions are welcome — bug reports, new analyzers, performance work, and docs.
            Read <code className="text-accent">CONTRIBUTING.md</code> and open an issue or PR on{" "}
            <a href={GITHUB} className="text-accent hover:underline">
              GitHub
            </a>
            . Security issues go through private reporting — see{" "}
            <code className="text-accent">SECURITY.md</code>.
          </p>
        </section>

        <section id="contact">
          <div className="rounded-sm border border-accent/30 bg-accent/5 p-6">
            <div className="mb-2 font-bold text-accent">Ready to scan your own repo?</div>
            <p className="mb-4 text-sm text-secondary">Five-minute install. One command. One report.</p>
            <a
              href={GITHUB}
              className="inline-flex items-center gap-2 rounded-sm border border-accent/40 px-4 py-3 text-sm text-accent transition-colors hover:bg-accent/10"
            >
              View on GitHub →
            </a>
          </div>
        </section>
      </main>
    </>
  );
}
