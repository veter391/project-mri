import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-start justify-center px-6">
      <p className="mb-4 text-xs tracking-widest text-accent">// 404 · not found</p>
      <h1 className="mb-4 text-3xl font-bold sm:text-4xl">
        That page isn&apos;t in this repository.
      </h1>
      <p className="mb-8 text-sm text-secondary">
        The route you followed doesn&apos;t exist. Head back to the scan.
      </p>
      <Link
        href="/"
        className="inline-flex items-center gap-2 rounded-sm border border-accent/40 px-4 py-3 text-sm text-accent transition-colors hover:bg-accent/10"
      >
        ← Back home
      </Link>
    </main>
  );
}
