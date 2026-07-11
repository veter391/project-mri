export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-start justify-center px-6">
      <p className="mb-3 text-xs tracking-widest text-accent">// 404</p>
      <h1 className="mb-4 text-2xl font-bold">Not found</h1>
      <a href="/dashboard/" className="text-sm text-accent hover:underline">
        ← Back to dashboard
      </a>
    </main>
  );
}
