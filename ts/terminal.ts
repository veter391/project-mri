/**
 * PROJECT MRI — Terminal animations
 * Typewriter · count-up · progress bar fill · terminal feed
 */

interface TypeOpts {
  speed?: number;     // ms per char
  startDelay?: number; // ms before starting
  cursor?: boolean;    // show blinking cursor at end
}

/**
 * Type text into an element character-by-character.
 * The element should have data-type="<text>" or you can pass text directly.
 */
export function typeInto(el: HTMLElement, text: string, opts: TypeOpts = {}): Promise<void> {
  const speed = opts.speed ?? 28;
  const startDelay = opts.startDelay ?? 0;
  const showCursor = opts.cursor ?? false;

  return new Promise((resolve) => {
    let i = 0;
    el.textContent = '';
    el.classList.add('is-typing');
    const start = () => {
      const tick = () => {
        if (i < text.length) {
          el.textContent += text.charAt(i++);
          window.setTimeout(tick, speed);
        } else {
          el.classList.remove('is-typing');
          if (showCursor) el.classList.add('is-done');
          resolve();
        }
      };
      tick();
    };
    window.setTimeout(start, startDelay);
  });
}

/**
 * Animate all elements with [data-type] on the page, sequentially.
 */
export function typeAllSequential(selector = '[data-type]', delayBetween = 120): void {
  const elements = Array.from(document.querySelectorAll<HTMLElement>(selector));
  let cumulative = 0;
  for (const el of elements) {
    const text = el.dataset.type ?? '';
    const speed = parseInt(el.dataset.typeSpeed ?? '24', 10);
    window.setTimeout(() => {
      void typeInto(el, text, { speed });
    }, cumulative);
    cumulative += text.length * speed + delayBetween;
  }
}

/**
 * Animate all elements with [data-count] to a target number with easing.
 */
export function countUpAll(selector = '[data-count]', duration = 1800): void {
  document.querySelectorAll<HTMLElement>(selector).forEach((el) => {
    const target = parseFloat(el.dataset.count ?? '0');
    const suffix = el.dataset.countSuffix ?? '';
    const prefix = el.dataset.countPrefix ?? '';
    const start = performance.now();
    const decimals = parseInt(el.dataset.countDecimals ?? '0', 10);
    const formatter = new Intl.NumberFormat('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      const val = target * eased;
      el.textContent = prefix + formatter.format(val) + suffix;
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

/**
 * Animate progress bars (data-fill = target percentage).
 */
export function fillProgressBars(selector = '[data-fill]', duration = 1400): void {
  document.querySelectorAll<HTMLElement>(selector).forEach((el) => {
    const target = parseFloat(el.dataset.fill ?? '0');
    const fillEl = el.querySelector<HTMLElement>('.monitor__fill, .stat-bar__fill');
    if (!fillEl) return;
    window.setTimeout(() => {
      fillEl.style.width = `${target}%`;
    }, 200);
  });
}

/**
 * Live event feed — adds an item at the bottom and shifts if needed.
 */
interface FeedItem {
  time: string;
  tag: string;
  msg: string;
  level?: 'ok' | 'warn' | 'alert' | 'info';
}

const FEED_DEMO: ReadonlyArray<FeedItem> = [
  { time: '14:22:08', tag: 'SCAN',  msg: 'started analysis · /repo/project-mri · 247 files · 4,812 commits', level: 'info' },
  { time: '14:22:11', tag: 'GIT',   msg: 'commit history extracted · 4,812 commits · 38 contributors', level: 'info' },
  { time: '14:22:14', tag: 'CODE',  msg: 'tree-sitter AST parsed · 18,452 functions · 247 files', level: 'info' },
  { time: '14:22:18', tag: 'GRAPH', msg: 'dependency graph built · 1,247 edges · 8 cycles detected', level: 'warn' },
  { time: '14:22:21', tag: 'SCORE', msg: 'architecture_health = 71/100 · technical_debt = 23.4/100', level: 'info' },
  { time: '14:22:23', tag: 'OWNER', msg: 'bus_factor = 4 · knowledge_islands = 2 modules', level: 'warn' },
  { time: '14:22:26', tag: 'AI',    msg: 'ai_influence = 18.2% · 4 large commits flagged', level: 'info' },
  { time: '14:22:28', tag: 'DONE',  msg: 'analysis complete · 20.4s · ./mri-report.html', level: 'ok' },
];

export function mountDemoFeed(host: HTMLElement): void {
  host.innerHTML = '';
  const list = document.createElement('div');
  list.className = 'demo-feed__list';
  host.appendChild(list);

  let idx = 0;
  function push(): void {
    if (idx >= FEED_DEMO.length) {
      // Loop with a small pause
      window.setTimeout(() => { idx = 0; push(); }, 4500);
      return;
    }
    const item = FEED_DEMO[idx++];
    const row = document.createElement('div');
    row.className = 'demo-feed__row';
    row.innerHTML = `
      <span class="demo-feed__time">${item.time}</span>
      <span class="demo-feed__tag tag--${item.level ?? 'info'}">${item.tag}</span>
      <span class="demo-feed__msg">${item.msg}</span>
    `;
    list.appendChild(row);
    // Auto-scroll list to bottom if it overflows
    host.scrollTop = host.scrollHeight;
    window.setTimeout(push, 900 + Math.random() * 600);
  }
  push();
}

/**
 * Initialize all terminal animations on the page.
 */
export function mountTerminal(): void {
  typeAllSequential();
  countUpAll();
  fillProgressBars();

  document.querySelectorAll<HTMLElement>('.demo-feed').forEach(mountDemoFeed);
}

/**
 * Re-run animations on demand (used by SPA navigation).
 * Resets [data-type] text to empty so typeInto replays.
 */
export function remountTerminal(): void {
  document.querySelectorAll<HTMLElement>('[data-type]').forEach((el) => {
    el.textContent = '';
    el.classList.remove('is-done');
  });
  // Re-bind demo feed containers (they were replaced with SPA swap)
  document.querySelectorAll<HTMLElement>('.demo-feed').forEach((host) => {
    host.innerHTML = '';
  });
  mountTerminal();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mountTerminal);
} else {
  mountTerminal();
}

// SPA re-mount hook
document.addEventListener('mri:remount', () => remountTerminal());