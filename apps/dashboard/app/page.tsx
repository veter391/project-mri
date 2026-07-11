"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  clearToken,
  getToken,
  listScans,
  login,
  setToken,
  type Scan,
} from "@/lib/api";

export default function Dashboard() {
  const [authed, setAuthed] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setAuthed(Boolean(getToken()));
    setReady(true);
  }, []);

  if (!ready) return null;
  return authed ? (
    <Overview
      onLogout={() => {
        clearToken();
        setAuthed(false);
      }}
    />
  ) : (
    <Login onLogin={() => setAuthed(true)} />
  );
}

function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { token } = await login(username, password);
      setToken(token);
      onLogin();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Invalid credentials." : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6">
      <p className="mb-2 text-xs tracking-widest text-accent">// project-mri</p>
      <h1 className="mb-6 text-2xl font-bold">Sign in</h1>
      <form onSubmit={submit} className="space-y-4">
        <label className="block text-sm">
          <span className="mb-1 block text-mute">Username</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full rounded-sm border border-line-2 bg-card px-3 py-2 outline-none focus:border-accent"
            autoComplete="username"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-mute">Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-sm border border-line-2 bg-card px-3 py-2 outline-none focus:border-accent"
            autoComplete="current-password"
          />
        </label>
        {error ? <p className="text-sm text-alert">{error}</p> : null}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-sm border border-accent/50 bg-accent/10 py-2 text-sm text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

const BAND = (h?: number) =>
  h == null ? "text-mute" : h >= 75 ? "text-ok" : h >= 50 ? "text-warn" : "text-alert";

function Overview({ onLogout }: { onLogout: () => void }) {
  const [scans, setScans] = useState<Scan[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await listScans();
      setScans(data.scans);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return onLogout();
      setError("Could not load scans.");
    }
  }, [onLogout]);

  useEffect(() => {
    void load();
  }, [load]);

  const healths = (scans ?? []).map((s) => s.score?.health).filter((h): h is number => h != null);
  const avg = healths.length ? Math.round(healths.reduce((a, b) => a + b, 0) / healths.length) : null;

  return (
    <main className="mx-auto max-w-5xl px-6">
      <header className="flex items-center justify-between border-b border-line py-4">
        <div className="flex items-center gap-2 font-bold">
          <span className="text-accent">●</span> project-mri
        </div>
        <button onClick={onLogout} className="text-sm text-mute hover:text-accent">
          sign out
        </button>
      </header>

      <section className="grid gap-3 py-8 sm:grid-cols-3">
        <Stat label="Total scans" value={scans ? String(scans.length) : "—"} />
        <Stat label="Average health" value={avg != null ? String(avg) : "—"} className={BAND(avg ?? undefined)} />
        <Stat label="Latest" value={scans?.[0]?.project_name ?? "—"} />
      </section>

      <section className="pb-16">
        <h2 className="mb-3 text-xs tracking-widest text-mute">/// recent scans</h2>
        {error ? (
          <p className="text-sm text-alert">{error}</p>
        ) : scans == null ? (
          <p className="text-sm text-mute">Loading…</p>
        ) : scans.length === 0 ? (
          <p className="text-sm text-mute">
            No scans yet. Run <code className="text-accent">mri scan /path/to/repo</code>.
          </p>
        ) : (
          <div className="overflow-hidden rounded-sm border border-line">
            <table className="w-full text-left text-[13px]">
              <thead className="bg-deep text-mute">
                <tr>
                  <th className="px-4 py-2 font-normal">Project</th>
                  <th className="px-4 py-2 font-normal">Status</th>
                  <th className="px-4 py-2 font-normal">Health</th>
                  <th className="px-4 py-2 font-normal">Started</th>
                </tr>
              </thead>
              <tbody>
                {scans.map((s) => (
                  <tr key={s.scan_uuid} className="border-t border-line">
                    <td className="px-4 py-2">{s.project_name}</td>
                    <td className="px-4 py-2 text-mute">{s.status}</td>
                    <td className={`px-4 py-2 ${BAND(s.score?.health)}`}>{s.score?.health ?? "—"}</td>
                    <td className="px-4 py-2 text-mute">{new Date(s.started_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="rounded-sm border border-line bg-card p-5">
      <div className="mb-1 text-xs text-mute">{label}</div>
      <div className={`text-2xl font-bold ${className ?? ""}`}>{value}</div>
    </div>
  );
}
