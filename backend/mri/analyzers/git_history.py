"""Git history analyzer.

Computes:
  - Hotspots: files with most commits + LOC churn
  - Bus factor: minimum contributors covering 80% of changes
  - Knowledge islands: modules touched by only 1-2 people
  - Commit cadence: bursts vs lulls (rough)

Score: starts at 100, subtracts weighted penalties.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from mri.analyzers.base import BaseAnalyzer, ScanContext


class GitHistoryAnalyzer(BaseAnalyzer):
    name = "git_history"
    description = "Hotspots, bus factor, knowledge islands from commit history"
    score_label = "history_health"
    weight = 1.0

    # Tunables
    HOTSPOT_TOP_N = 10
    BUS_FACTOR_TARGET = 0.80  # 80% of changes covered
    KNOWLEDGE_ISLAND_MAX_AUTHORS = 1

    async def analyze(self, ctx: ScanContext) -> None:  # type: ignore[override]
        self._start()
        try:
            git = ctx.git
            if git is None:
                # No git repo → score 50, info finding
                self._set_score(50.0, ["no git history available"])
                self._add_finding(
                    severity="info",
                    category="no_git",
                    title="No git history",
                    description="This directory is not a git repository. Run `git init` and commit your code.",
                )
                self._finish_ok()
                return
            # Resolve a usable branch — fall back to active if requested branch is missing
            branch = ctx.branch
            try:
                git.rev_parse("--verify", f"{branch}^{{commit}}")
            except Exception:  # nosem: bandit  # branch name may be invalid; fall back
                try:
                    branch = git.active_branch.name
                except Exception:  # nosem: bandit  # detached HEAD or unborn branch
                    branch = "HEAD"
            commits = list(git.iter_commits(branch, max_count=10000))
            if not commits:
                self._set_score(50.0, ["no commits found on branch " + ctx.branch])
                self._add_finding(
                    severity="info",
                    category="empty_history",
                    title="No commits found",
                    description=f"Branch {ctx.branch} has no commits. Nothing to analyze.",
                )
                self._finish_ok()
                return

            # Per-file: total churn (insertions + deletions), commit count, authors
            file_churn: dict[str, int] = Counter()
            file_commits: dict[str, int] = Counter()
            file_authors: dict[str, set[str]] = defaultdict(set)
            author_total: Counter[str] = Counter()

            for commit in commits:
                author = (commit.author.email or commit.author.name or "unknown").lower()
                author_total[author] += 1
                try:
                    stats = commit.stats
                except Exception:
                    continue  # nosec B112
                for path_str in stats.files.keys():
                    if ctx.is_excluded(path_str):
                        continue
                    fstats = stats.files[path_str]
                    churn = (fstats.get("lines", 0) if isinstance(fstats, dict) else getattr(fstats, "lines", 0)) \
                        + (fstats.get("deletions", 0) if isinstance(fstats, dict) else getattr(fstats, "deletions", 0))
                    file_churn[path_str] += churn
                    file_commits[path_str] += 1
                    file_authors[path_str].add(author)

            # --- Hotspots (files with high churn AND many commits) ---
            hotspots = []
            for path_str, churn in file_churn.most_common(self.HOTSPOT_TOP_N * 2):
                ccount = file_commits[path_str]
                # Composite hotspot score: log(churn) * commits
                if ccount < 3 or churn < 50:
                    continue
                composite = ccount * (1 + (churn ** 0.5) / 10)
                hotspots.append({
                    "path": path_str,
                    "commits": ccount,
                    "churn": churn,
                    "authors": len(file_authors[path_str]),
                    "composite": round(composite, 1),
                })
                if len(hotspots) >= self.HOTSPOT_TOP_N:
                    break

            for h in hotspots:
                sev = "high" if h["composite"] > 80 else "medium" if h["composite"] > 40 else "low"
                self._add_finding(
                    severity=sev,
                    category="hotspot",
                    title=f"Hotspot: {h['path']}",
                    description=(
                        f"{h['commits']} commits touching this file with ~{h['churn']:,} lines "
                        f"of churn. {h['authors']} author(s). High-churn files are risky to refactor."
                    ),
                    target_path=h["path"],
                    score=min(100.0, h["composite"]),
                    data=h,
                )

            # --- Bus factor: minimum authors covering BUS_FACTOR_TARGET of changes ---
            sorted_authors = sorted(author_total.items(), key=lambda kv: -kv[1])
            total_changes = sum(author_total.values())
            cumulative = 0
            bus_authors = []
            for author, count in sorted_authors:
                bus_authors.append(author)
                cumulative += count
                if cumulative / max(total_changes, 1) >= self.BUS_FACTOR_TARGET:
                    break
            bus_factor = len(bus_authors)

            # --- Knowledge islands: files with <=1 author ---
            island_files = [
                p for p, authors in file_authors.items()
                if len(authors) <= self.KNOWLEDGE_ISLAND_MAX_AUTHORS and file_commits[p] >= 5
            ]
            for path_str in island_files[:10]:
                self._add_finding(
                    severity="medium",
                    category="knowledge_island",
                    title=f"Knowledge island: {path_str}",
                    description=(
                        f"This file was only touched by {len(file_authors[path_str])} author(s) "
                        f"across {file_commits[path_str]} commits. Bus-factor risk: if that person "
                        f"is unavailable, context is lost."
                    ),
                    target_path=path_str,
                    score=60.0,
                )

            # --- Cadence (last 90 days vs prior 90 days) ---
            cadence = self._cadence(commits)

            # --- Compose score ---
            score = 100.0
            contributors: list[str] = []
            if hotspots:
                # Top hotspot penalty
                top = hotspots[0]
                penalty = min(40.0, top["composite"] * 0.4)
                score -= penalty
                contributors.append(
                    f"top hotspot '{top['path']}' = {top['composite']:.1f} (-{penalty:.1f})"
                )
            # Bus factor: ideal is >=5, critical is 1
            if bus_factor == 1:
                score -= 35
                contributors.append("bus_factor = 1 (single point of failure) (-35.0)")
            elif bus_factor == 2:
                score -= 20
                contributors.append("bus_factor = 2 (-20.0)")
            elif bus_factor <= 4:
                score -= 8
                contributors.append(f"bus_factor = {bus_factor} (-8.0)")
            else:
                contributors.append(f"bus_factor = {bus_factor} (healthy)")
            # Knowledge islands penalty
            if island_files:
                island_pen = min(15.0, len(island_files) * 1.5)
                score -= island_pen
                contributors.append(
                    f"{len(island_files)} knowledge islands (-{island_pen:.1f})"
                )

            self._set_score(max(0.0, score), contributors)
            self.run.signals = {
                "commit_count": len(commits),
                "files_touched": len(file_churn),
                "authors": len(author_total),
                "bus_factor": bus_factor,
                "top_hotspots": hotspots[:5],
                "knowledge_islands": len(island_files),
                "cadence": cadence,
                "total_churn": sum(file_churn.values()),
            }
            self._finish_ok()
        except Exception as exc:  # pragma: no cover
            self._finish_err(f"{type(exc).__name__}: {exc}")
            raise

    @staticmethod
    def _cadence(commits: list) -> dict:
        if not commits:
            return {}
        now = datetime.utcnow()
        last_90 = 0
        prior_90 = 0
        for c in commits:
            d = c.committed_datetime.replace(tzinfo=None)
            delta_days = (now - d).days
            if delta_days <= 90:
                last_90 += 1
            elif delta_days <= 180:
                prior_90 += 1
        if prior_90 == 0:
            ratio = None
        else:
            ratio = round(last_90 / max(prior_90, 1), 2)
        return {
            "last_90_days": last_90,
            "prior_90_days": prior_90,
            "ratio": ratio,
        }