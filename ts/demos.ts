/**
 * PROJECT MRI — Interactive demos
 * Architecture graph (Canvas 2D), pipeline simulator (no real engine, but faithful step-by-step).
 */

interface GraphNode {
  id: string;
  label: string;
  x: number;
  y: number;
  layer: number; // 0..3 vertical layout
}

interface GraphEdge {
  from: string;
  to: string;
}

/**
 * Render the architecture pipeline diagram on a <canvas>.
 * Draws nodes (analyzer stages) connected by edges.
 * Layers are positioned HORIZONTALLY with column headers above the canvas.
 */
export function renderArchitectureGraph(canvas: HTMLCanvasElement): void {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // Hi-DPI
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const cssW = canvas.clientWidth;
  const cssH = canvas.clientHeight;
  canvas.width = cssW * dpr;
  canvas.height = cssH * dpr;
  ctx.scale(dpr, dpr);

  // Dark background
  ctx.fillStyle = '#06080C';
  ctx.fillRect(0, 0, cssW, cssH);

  // Subtle grid
  ctx.strokeStyle = 'rgba(244, 168, 71, 0.05)';
  ctx.lineWidth = 1;
  for (let x = 0; x < cssW; x += 32) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, cssH); ctx.stroke();
  }
  for (let y = 0; y < cssH; y += 32) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(cssW, y); ctx.stroke();
  }

  // Vertical separators + column headers for each stage
  const W = cssW;
  const H = cssH;
  const HEADER_H = 28;
  const stages: ReadonlyArray<{ x: number; label: string }> = [
    { x: W * 0.10, label: 'INPUT' },
    { x: W * 0.30, label: 'ORCHESTRATOR' },
    { x: W * 0.55, label: 'ANALYZERS' },
    { x: W * 0.80, label: 'STORAGE' },
    { x: W * 0.95, label: 'OUTPUT' },
  ];

  // Draw column headers at the top
  ctx.fillStyle = 'rgba(244, 168, 71, 0.95)';
  ctx.font = '700 10px "JetBrains Mono", monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  stages.forEach((stage) => {
    ctx.fillText(stage.label, stage.x, 8);
  });

  // Vertical column separators (subtle)
  ctx.strokeStyle = 'rgba(244, 168, 71, 0.10)';
  ctx.lineWidth = 1;
  for (let i = 1; i < stages.length; i++) {
    const xMid = (stages[i - 1].x + stages[i].x) / 2;
    ctx.beginPath();
    ctx.moveTo(xMid, HEADER_H + 4);
    ctx.lineTo(xMid, H - 4);
    ctx.stroke();
  }

  // Layers: [input] → [orchestrator] → [analyzers] → [storage] → [output]
  const layers: ReadonlyArray<{ x: number; nodes: ReadonlyArray<{ id: string; label: string }> }> = [
    { x: stages[0].x, nodes: [
      { id: 'repo', label: 'Git Repo' },
    ]},
    { x: stages[1].x, nodes: [
      { id: 'orch', label: 'Orchestrator' },
    ]},
    { x: stages[2].x, nodes: [
      { id: 'git',   label: 'Git History' },
      { id: 'code',  label: 'Code Struct.' },
      { id: 'graph', label: 'Graph Builder' },
      { id: 'score', label: 'Scoring Engine' },
      { id: 'ai',    label: 'AI Impact' },
    ]},
    { x: stages[3].x, nodes: [
      { id: 'store', label: 'SQLite + DuckDB' },
    ]},
    { x: stages[4].x, nodes: [
      { id: 'out', label: 'Reports + UI' },
    ]},
  ];

  // Compute node positions (centered vertically below header)
  const nodes: GraphNode[] = [];
  const usableH = H - HEADER_H - 16;
  for (const layer of layers) {
    const totalH = layer.nodes.length * 52;
    const startY = HEADER_H + 16 + (usableH - totalH) / 2;
    layer.nodes.forEach((n, i) => {
      nodes.push({
        id: n.id,
        label: n.label,
        x: layer.x,
        y: startY + i * 52 + 18,
        layer: layers.indexOf(layer),
      });
    });
  }

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  const edges: GraphEdge[] = [
    { from: 'repo',  to: 'orch' },
    { from: 'orch', to: 'git' },
    { from: 'orch', to: 'code' },
    { from: 'orch', to: 'graph' },
    { from: 'orch', to: 'score' },
    { from: 'orch', to: 'ai' },
    { from: 'git',   to: 'store' },
    { from: 'code',  to: 'store' },
    { from: 'graph', to: 'store' },
    { from: 'score', to: 'store' },
    { from: 'ai',    to: 'store' },
    { from: 'store', to: 'out' },
  ];

  // Draw edges
  ctx.strokeStyle = 'rgba(244, 168, 71, 0.45)';
  ctx.lineWidth = 1;
  for (const e of edges) {
    const a = nodeMap.get(e.from);
    const b = nodeMap.get(e.to);
    if (!a || !b) continue;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    const midX = (a.x + b.x) / 2;
    ctx.bezierCurveTo(midX, a.y, midX, b.y, b.x, b.y);
    ctx.stroke();

    // Arrow head at b
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const angle = Math.atan2(dy, dx);
    const ah = 6;
    ctx.beginPath();
    ctx.moveTo(b.x - Math.cos(angle) * 18, b.y - Math.sin(angle) * 18);
    ctx.lineTo(
      b.x - Math.cos(angle) * 18 - Math.cos(angle - 0.4) * ah,
      b.y - Math.sin(angle) * 18 - Math.sin(angle - 0.4) * ah,
    );
    ctx.lineTo(
      b.x - Math.cos(angle) * 18 - Math.cos(angle + 0.4) * ah,
      b.y - Math.sin(angle) * 18 - Math.sin(angle + 0.4) * ah,
    );
    ctx.closePath();
    ctx.fillStyle = 'rgba(244, 168, 71, 0.85)';
    ctx.fill();
  }

  // Draw nodes
  for (const n of nodes) {
    const w = 130;
    const h = 36;
    const x = n.x - w / 2;
    const y = n.y - h / 2;

    // Box
    ctx.fillStyle = '#0F131B';
    ctx.strokeStyle = '#F4A847';
    ctx.lineWidth = 1;
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);

    // Top accent line
    ctx.fillStyle = 'rgba(244, 168, 71, 0.4)';
    ctx.fillRect(x, y, w, 2);

    // Label
    ctx.fillStyle = '#F5F2EA';
    ctx.font = '600 11px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(n.label, n.x, n.y);
  }
}

/**
 * Interactive file-tree simulator — animated sample repo scan.
 */
export function mountFileTreeSimulator(host: HTMLElement): void {
  host.innerHTML = '';

  const files: ReadonlyArray<{ path: string; size: number; changes: number; owner: string; risk: 'low' | 'med' | 'high' }> = [
    { path: 'src/orchestrator/index.ts',  size: 4_812, changes: 47, owner: 'marcus',  risk: 'low' },
    { path: 'src/analyzers/git-history.ts', size: 8_241, changes: 89, owner: 'priya',   risk: 'med' },
    { path: 'src/analyzers/code-structure.ts', size: 12_904, changes: 124, owner: 'priya', risk: 'high' },
    { path: 'src/analyzers/graph-builder.ts', size: 6_553, changes: 73, owner: 'sofia', risk: 'med' },
    { path: 'src/analyzers/scoring.ts',     size: 5_219, changes: 92, owner: 'daniel', risk: 'high' },
    { path: 'src/analyzers/ai-impact.ts',   size: 3_471, changes: 41, owner: 'sofia',  risk: 'low' },
    { path: 'src/storage/sqlite.ts',       size: 2_138, changes: 18, owner: 'marcus', risk: 'low' },
    { path: 'src/storage/migrations/001_init.sql', size: 1_204, changes: 4, owner: 'marcus', risk: 'low' },
    { path: 'src/cli/typer.ts',            size: 982,   changes: 12, owner: 'marcus', risk: 'low' },
    { path: 'src/reports/html.ts',         size: 7_390, changes: 56, owner: 'sofia',  risk: 'med' },
    { path: 'src/reports/markdown.ts',     size: 1_847, changes: 23, owner: 'sofia',  risk: 'low' },
    { path: 'src/visualization/pyvis.ts',  size: 4_002, changes: 34, owner: 'priya',  risk: 'low' },
    { path: 'tests/analyzers/git.test.ts', size: 2_145, changes: 28, owner: 'marcus', risk: 'low' },
    { path: 'tests/analyzers/code.test.ts',size: 3_874, changes: 51, owner: 'priya',  risk: 'med' },
    { path: 'docs/architecture.md',        size: 14_532, changes: 22, owner: 'daniel', risk: 'low' },
  ];

  // Build table
  const table = document.createElement('table');
  table.className = 't-table';
  table.innerHTML = `
    <thead>
      <tr>
        <th>path</th>
        <th>size</th>
        <th>changes</th>
        <th>owner</th>
        <th>risk</th>
        <th style="width:140px">churn</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;
  const tbody = table.querySelector('tbody');
  if (!tbody) return;

  // Animate rows in
  files.forEach((f, i) => {
    const tr = document.createElement('tr');
    const churnPct = Math.min(100, Math.round((f.changes / 130) * 100));
    const churnClass = f.risk === 'high' ? 'monitor__fill--alert' : f.risk === 'med' ? 'monitor__fill--warn' : 'monitor__fill--ok';
    tr.innerHTML = `
      <td class="mono">${f.path}</td>
      <td class="num">${f.size.toLocaleString()}</td>
      <td class="num">${f.changes}</td>
      <td class="mono">@${f.owner}</td>
      <td><span class="status status--${f.risk === 'high' ? 'alert' : f.risk === 'med' ? 'warn' : 'ok'}">${f.risk.toUpperCase()}</span></td>
      <td>
        <div class="monitor" style="border:none;padding:0;">
          <div class="monitor__bar" style="grid-column:1/-1;margin-top:0;">
            <div class="monitor__fill ${churnClass}" data-fill-target="${churnPct}" style="width:0%"></div>
          </div>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
    // Fade in
    tr.style.opacity = '0';
    tr.style.transition = 'opacity 200ms';
    window.setTimeout(() => { tr.style.opacity = '1'; }, 80 + i * 60);
    // Animate the bar
    window.setTimeout(() => {
      const fill = tr.querySelector<HTMLElement>('.monitor__fill');
      if (fill) fill.style.width = `${churnPct}%`;
    }, 400 + i * 60);
  });

  host.appendChild(table);
}