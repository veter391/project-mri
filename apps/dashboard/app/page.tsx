"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  clearToken,
  getFusion,
  getToken,
  listProjects,
  listScans,
  login,
  setToken,
  type FusionFile,
  type Project,
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
  if (!authed) return <Login onLogin={() => setAuthed(true)} />;
  const onLogout = () => {
    clearToken();
    setAuthed(false);
  };
  return <AuthedApp onLogout={onLogout} />;
}

function AuthedApp({ onLogout }: { onLogout: () => void }) {
  const [tab, setTab] = useState<"overview" | "fusion">("overview");
  return tab === "overview" ? (
    <Overview onLogout={onLogout} onFusion={() => setTab("fusion")} />
  ) : (
    <FusionView onLogout={onLogout} onOverview={() => setTab("overview")} />
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

const healthOf = (s: Scan) => s.overall_health ?? undefined;

// started_at may be ISO (completed scans) or SQLite "YYYY-MM-DD HH:MM:SS" UTC
// (pending). Normalize the latter so it doesn't render "Invalid Date".
function fmtDate(raw: string): string {
  const iso = /[T]|[+Z]$/.test(raw) ? raw : `${raw.replace(" ", "T")}Z`;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? raw : d.toLocaleString();
}

function Overview({ onLogout, onFusion }: { onLogout: () => void; onFusion: () => void }) {
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

  const healths = (scans ?? []).map(healthOf).filter((h): h is number => h != null);
  const avg = healths.length ? Math.round(healths.reduce((a, b) => a + b, 0) / healths.length) : null;

  return (
    <main className="mx-auto max-w-5xl px-6">
      <NavHeader active="overview" onFusion={onFusion} onLogout={onLogout} />

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
                    <td className={`px-4 py-2 ${BAND(healthOf(s))}`}>{healthOf(s) ?? "—"}</td>
                    <td className="px-4 py-2 text-mute">{fmtDate(s.started_at)}</td>
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

// Each factor name maps to a lens (its colour and label). Unknown names fall
// back to a mute generic, so a new backend factor renders sanely without a code
// change here.
const LENS: Record<string, { label: string; cls: string }> = {
  risk: { label: "risk", cls: "text-mute" },
  ai_authorship: { label: "authorship", cls: "text-accent" },
  ai_evidence: { label: "authorship", cls: "text-accent" },
  weighted_risk: { label: "authorship", cls: "text-accent" },
  sessions: { label: "provenance", cls: "text-ok" },
  decisions: { label: "provenance", cls: "text-ok" },
  consequences: { label: "consequence", cls: "text-warn" },
};

function NavHeader({
  active,
  onOverview,
  onFusion,
  onLogout,
}: {
  active: "overview" | "fusion";
  onOverview?: () => void;
  onFusion?: () => void;
  onLogout: () => void;
}) {
  const link = "min-h-11 text-mute hover:text-accent";
  return (
    <header className="flex items-center justify-between border-b border-line py-4">
      <div className="flex items-center gap-2 font-bold">
        <span className="text-accent">●</span> project-mri
      </div>
      <nav className="flex items-center gap-5 text-sm">
        {active === "overview" ? (
          <span className="text-accent">overview</span>
        ) : (
          <button onClick={onOverview} className={link}>overview</button>
        )}
        {active === "fusion" ? (
          <span className="text-accent">fusion</span>
        ) : (
          <button onClick={onFusion} className={link}>fusion</button>
        )}
        <button onClick={onLogout} className={link}>sign out</button>
      </nav>
    </header>
  );
}

function FusionView({ onLogout, onOverview }: { onLogout: () => void; onOverview: () => void }) {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [files, setFiles] = useState<FusionFile[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then((d) => {
        setProjects(d.projects);
        if (d.projects.length) setSelected(d.projects[0].id);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) return onLogout();
        setError("Could not load projects.");
      });
  }, [onLogout]);

  useEffect(() => {
    if (selected == null) return;
    setFiles(null);
    getFusion(selected)
      .then((d) => setFiles(d.files))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) return onLogout();
        setError("Could not load fusion data.");
      });
  }, [selected, onLogout]);

  return (
    <main className="mx-auto max-w-5xl px-6">
      <NavHeader active="fusion" onOverview={onOverview} onLogout={onLogout} />
      <section className="py-8">
        <h1 className="mb-1 text-xl font-bold">AI provenance &amp; decisions</h1>
        <p className="mb-6 max-w-2xl text-sm text-secondary">
          Who authored the riskiest files, traced to sessions, with the decisions and
          measured consequences behind them. Correlation, never causation.
        </p>

        {error ? (
          <p className="text-sm text-alert">{error}</p>
        ) : projects == null ? (
          <p className="text-sm text-mute">Loading…</p>
        ) : projects.length === 0 ? (
          <p className="text-sm text-mute">
            No projects yet. Run <code className="text-accent">mri scan /path/to/repo</code>.
          </p>
        ) : (
          <>
            <label className="mb-6 block text-sm">
              <span className="mb-1 block text-mute">Project</span>
              <select
                value={selected ?? ""}
                onChange={(e) => setSelected(Number(e.target.value))}
                className="min-h-11 rounded-sm border border-line-2 bg-card px-3 py-2 outline-none focus:border-accent"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>

            {files == null ? (
              <p className="text-sm text-mute">Loading…</p>
            ) : files.length === 0 ? (
              <p className="text-sm text-mute">
                No fusion evidence yet. Run{" "}
                <code className="text-accent">mri fusion /path/to/repo</code>.
              </p>
            ) : (
              <div className="space-y-3">
                {files.map((f) => (
                  <FusionCard key={f.file} file={f} />
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </main>
  );
}

function FusionCard({ file }: { file: FusionFile }) {
  return (
    <article className="rounded-sm border border-line bg-card p-4">
      <div className="mb-2 font-bold break-all text-accent">{file.file}</div>
      <p className="mb-3 text-[13px] text-secondary">{file.prose}</p>
      <ul className="space-y-1">
        {file.factors.map((factor, i) => {
          const lens = LENS[factor.name] ?? { label: factor.name, cls: "text-mute" };
          return (
            <li key={i} className="grid grid-cols-[96px_1fr] gap-3 text-[12px]">
              <span className={`uppercase tracking-wider ${lens.cls}`}>{lens.label}</span>
              <span className="text-secondary">{factor.statement}</span>
            </li>
          );
        })}
      </ul>
    </article>
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
