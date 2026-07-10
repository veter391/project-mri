/**
 * PROJECT MRI — Shared chrome + SPA navigation
 * Injects nav, status bar, footer.
 * Intercepts internal link clicks → fetches .html → swaps <main> content
 * so the site works on static hosts (no URL rewrite needed).
 */

const SITE_NAME = 'PROJECT_MRI';

const NAV_LINKS: ReadonlyArray<{ route: string; label: string }> = [
  { route: '/',          label: '~ /' },
  { route: '/features',  label: '~ /features' },
  { route: '/architecture', label: '~ /architecture' },
  { route: '/install',   label: '~ /install' },
  { route: '/demo/',     label: '~ /demo' },
  { route: '/manifesto', label: '~ /manifesto' },
  { route: '/roadmap',   label: '~ /roadmap' },
  { route: '/about',     label: '~ /about' },
];

const FOOTER_COLUMNS: ReadonlyArray<{
  title: string;
  links: ReadonlyArray<{ href: string; label: string }>;
}> = [
  {
    title: 'Project',
    links: [
      { href: './features',     label: 'Features' },
      { href: './architecture', label: 'Architecture' },
      { href: './roadmap',      label: 'Roadmap' },
      { href: './manifesto',    label: 'Manifesto' },
    ],
  },
  {
    title: 'Get Started',
    links: [
      { href: './install', label: 'Install' },
      { href: 'https://github.com/project-mri/project-mri', label: 'GitHub ↗' },
      { href: './about',   label: 'Community' },
    ],
  },
  {
    title: 'Resources',
    links: [
      { href: './about',           label: 'About' },
      { href: './about#contact',   label: 'Contact' },
      { href: './about#license',   label: 'License' },
    ],
  },
];

export function getCurrentRoute(): string {
  const body = document.body;
  return body.dataset.route || '/';
}

function navHTML(currentRoute: string): string {
  const links = NAV_LINKS.map((l) => {
    const isActive = l.route === currentRoute;
    const active = isActive ? ' is-active' : '';
    const current = isActive ? ' aria-current="page"' : '';
    return `<a href="${l.route}" class="nav-link${active}"${current} data-spa-link>${l.label}</a>`;
  }).join('');

  return `
    <a href="#main-content" class="skip-link">Skip to main content</a>
    <nav class="nav" role="navigation" aria-label="Primary">
      <div class="nav__inner">
        <a href="/" class="nav__brand" data-spa-link aria-label="Project MRI — home">
          <svg class="nav__brand-mark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <circle cx="12" cy="12" r="9"/>
            <circle cx="12" cy="12" r="3"/>
            <path d="M12 1v3M12 20v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M1 12h3M20 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>
          </svg>
          project-mri
        </a>
        <div class="nav__links" id="nav-links">${links}</div>
        <button class="nav__burger" type="button" aria-label="Toggle navigation menu" aria-expanded="false" aria-controls="nav-links">
          <span></span>
        </button>
        <div class="nav__meta">
          <a href="https://github.com/project-mri/project-mri" target="_blank" rel="noopener">github ↗</a>
          <span>v0.1.0</span>
        </div>
      </div>
    </nav>
  `;
}

function statusBarHTML(): string {
  const time = formatTime();
  return `
    <div class="status-bar" role="status" aria-label="System status">
      <div class="status-bar__group">
        <span class="status-bar__live"><span class="status-bar__dot"></span>local-first</span>
        <span>offline-ready</span>
        <span class="is-warn">mit · agpl-tbd</span>
      </div>
      <div class="status-bar__group">
        <span id="status-time">${time} UTC</span>
        <span>build · ${SITE_NAME}</span>
      </div>
    </div>
  `;
}

function footerHTML(): string {
  const cols = FOOTER_COLUMNS.map((col) => `
    <div class="footer__col">
      <h4>${col.title}</h4>
      <ul>
        ${col.links.map((l) => `<li><a href="${l.href}" data-spa-link>${l.label}</a></li>`).join('')}
      </ul>
    </div>
  `).join('');

  const year = new Date().getFullYear();

  return `
    <footer class="footer">
      <div class="footer__inner">
        <div>
          <div class="footer__brand">project-mri</div>
          <p class="t-small" style="max-width:36ch;line-height:1.6;text-transform:none;letter-spacing:0;">
            "MRI scan" for your software project.<br>
            Local-first. Open source. Explainable.
          </p>
        </div>
        ${cols}
      </div>
      <div class="footer__bottom">
        <span>© ${year} project-mri contributors · MIT</span>
        <span>built with care · facts over magic scores</span>
      </div>
    </footer>
  `;
}

function formatTime(): string {
  const d = new Date();
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  const ss = String(d.getUTCSeconds()).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

/** Visually-hidden live region so screen readers hear route changes. */
function ensureLiveRegion(): HTMLElement {
  let region = document.getElementById('mri-live-region');
  if (!region) {
    region = document.createElement('div');
    region.id = 'mri-live-region';
    region.className = 'sr-only';
    region.setAttribute('aria-live', 'polite');
    region.setAttribute('aria-atomic', 'true');
    document.body.appendChild(region);
  }
  return region;
}

function announce(message: string): void {
  ensureLiveRegion().textContent = message;
}

/** Mobile navigation menu open/close (the burger). */
function setMobileMenu(open: boolean): void {
  const links = document.getElementById('nav-links');
  const burger = document.querySelector<HTMLButtonElement>('.nav__burger');
  if (links) links.classList.toggle('is-open', open);
  if (burger) burger.setAttribute('aria-expanded', open ? 'true' : 'false');
}

/**
 * SPA navigation + chrome interactions. Installed exactly once (guarded)
 * via event delegation, so it survives nav re-renders after each swap and
 * never accumulates duplicate document listeners.
 */
let interactionsInstalled = false;
function installSpaNavigation(): void {
  if (interactionsInstalled) return;
  interactionsInstalled = true;

  document.addEventListener('click', (e: MouseEvent) => {
    const el = e.target as HTMLElement;

    // Burger toggle
    const burger = el.closest('.nav__burger');
    if (burger) {
      const isOpen = burger.getAttribute('aria-expanded') === 'true';
      setMobileMenu(!isOpen);
      return;
    }

    // Internal SPA link
    const target = el.closest('a[data-spa-link]');
    if (!target) return;
    const anchor = target as HTMLAnchorElement;
    const href = anchor.getAttribute('href') || '';
    if (!href.startsWith('/')) return; // internal routes only
    if (anchor.target === '_blank' || href.startsWith('mailto:')) return;

    e.preventDefault();
    setMobileMenu(false); // close the menu when navigating
    navigateTo(href);
  });

  // Escape closes the mobile menu.
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Escape') setMobileMenu(false);
  });

  // Handle browser back/forward
  window.addEventListener('popstate', () => {
    const route = location.pathname === '/' ? '/' : '/' + location.pathname.replace(/^\/|\/$/g, '');
    navigateTo(route, false);
  });
}

async function navigateTo(href: string, pushState = true): Promise<void> {
  try {
    // Strip hash for fetching
    const [path, hash] = href.split('#');
    // Directory-based routes (e.g. /demo/) need ./demo/index.html
    // Root and other pages use ./<slug>.html
    let fetchPath: string;
    if (path === '/' || path === '') {
      fetchPath = '/';
    } else if (path.endsWith('/')) {
      fetchPath = `${path}index.html`;
    } else {
      fetchPath = `${path}.html`;
    }
    const res = await fetch(fetchPath, { cache: 'no-cache' });
    if (!res.ok) {
      // Fallback: hard navigation
      location.href = path + (hash ? '#' + hash : '');
      return;
    }
    const html = await res.text();

    // Parse the new HTML
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');

    // Swap content
    const newMain = doc.querySelector('main');
    const oldMain = document.querySelector('main');
    if (newMain && oldMain) {
      oldMain.innerHTML = newMain.innerHTML;
    }

    // Update body data-route for new active state
    const newRoute = doc.body.dataset.route || path;
    document.body.dataset.route = newRoute;

    // Update nav active state
    updateNavActive(newRoute);

    // Update document title
    document.title = doc.title;

    // Accessibility: move keyboard focus into the freshly-swapped content and
    // announce the new page, so keyboard and screen-reader users are not left
    // stranded on the stale link with no feedback.
    const focusMain = document.querySelector<HTMLElement>('main');
    if (focusMain) {
      focusMain.setAttribute('tabindex', '-1');
      focusMain.focus();
    }
    announce(doc.title);

    // Re-mount any page-specific JS (terminal animations, demos, etc.)
    remountPageFeatures();

    // Push state
    if (pushState) {
      const url = path + (hash ? '#' + hash : '');
      history.pushState({ route: newRoute }, '', url);
    }

    // Scroll to hash if present, else top
    if (hash) {
      const target = document.getElementById(hash);
      if (target) {
        // Wait one tick so layout settles
        requestAnimationFrame(() => {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
      }
    } else {
      window.scrollTo(0, 0);
    }
  } catch (err) {
    console.error('SPA nav failed:', err);
    // Hard navigation fallback
    location.href = href;
  }
}

function updateNavActive(route: string): void {
  document.querySelectorAll<HTMLAnchorElement>('.nav-link').forEach((a) => {
    const href = a.getAttribute('href');
    if (href === route) {
      a.classList.add('is-active');
      a.setAttribute('aria-current', 'page');
    } else {
      a.classList.remove('is-active');
      a.removeAttribute('aria-current');
    }
  });
}

/**
 * Re-trigger page-specific animations after SPA swap.
 * Dispatches a custom event that any module can listen to,
 * and also calls module-level reinit if available.
 */
function remountPageFeatures(): void {
  // Re-trigger typewriter, count-up, progress bars, feed
  document.dispatchEvent(new CustomEvent('mri:remount'));
  // Give modules a tick to react, then scroll the new content into view
}

/**
 * Inject nav + status bar + footer + SPA handlers into the page.
 * Idempotent — safe to call once per page.
 */
export function mountChrome(): void {
  const route = getCurrentRoute();
  const navHost = document.getElementById('site-nav');
  const statusHost = document.getElementById('site-status');
  const footerHost = document.getElementById('site-footer');
  const vignetteHost = document.getElementById('site-vignette');

  if (navHost) navHost.innerHTML = navHTML(route);
  if (statusHost) statusHost.innerHTML = statusBarHTML();
  if (footerHost) footerHost.innerHTML = footerHTML();
  if (vignetteHost) vignetteHost.innerHTML = '<div class="crt-vignette"></div>';

  installSpaNavigation();

  // Tick the status bar clock every second.
  window.setInterval(() => {
    const el = document.getElementById('status-time');
    if (el) el.textContent = `${formatTime()} UTC`;
  }, 1000);
}

// Auto-mount on DOMContentLoaded.
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mountChrome);
} else {
  mountChrome();
}

// Re-mount chrome (nav/status/footer) after SPA navigation
document.addEventListener('mri:remount', () => {
  // Re-render nav with active state updated
  const route = getCurrentRoute();
  const navHost = document.getElementById('site-nav');
  if (navHost) navHost.innerHTML = navHTML(route);
  // Re-attach SPA click handlers
  installSpaNavigation();
});

// Expose updateNavActive for the initial-routing fix in index.html
(window as unknown as { __mri_updateNavActive?: (r: string) => void }).__mri_updateNavActive = updateNavActive;