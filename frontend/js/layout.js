/**
 * Shared Navigation Shell, Formatting Utilities, Toast Notifications, and State Renderers.
 */
(function (global) {
  const NAV_ITEMS = [
    { section: 'Overview' },
    { id: 'dashboard', label: 'Dashboard', href: '/frontend/dashboard.html', icon: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>' },
    { id: 'sales', label: 'Sales Analytics', href: '/frontend/sales-analytics.html', icon: '<path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/>' },
    { section: 'Data Pipeline' },
    { id: 'upload', label: 'CSV Upload', href: '/frontend/csv-upload.html', icon: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>' },
    { id: 'datasets', label: 'Data Management', href: '/frontend/data-management.html', icon: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/>' },
    { section: 'Intelligence & ML' },
    { id: 'segmentation', label: 'Customer Segmentation', href: '/frontend/customer-segmentation.html', icon: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>' },
    { id: 'forecasting', label: 'Demand Forecasting', href: '/frontend/demand-forecasting.html', icon: '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>' },
    { id: 'alerts', label: 'Smart Alerts', href: '/frontend/smart-alerts.html', icon: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>' },
    { section: 'Outputs' },
    { id: 'reports', label: 'Reports', href: '/frontend/reports.html', icon: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>' },
    { id: 'settings', label: 'Settings', href: '/frontend/settings.html', icon: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>' },
  ];

  function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatCurrency(val) {
    const n = Number(val);
    if (!Number.isFinite(n)) return '—';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 2,
    }).format(n);
  }

  function formatNumber(val, decimals = 0) {
    const n = Number(val);
    if (!Number.isFinite(n)) return '—';
    return new Intl.NumberFormat('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(n);
  }

  function formatDate(val) {
    if (!val) return '—';
    const d = new Date(val);
    if (Number.isNaN(d.getTime())) return escapeHtml(val);
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  function ensureToastContainer() {
    let el = document.getElementById('toast-container');
    if (!el) {
      el = document.createElement('div');
      el.id = 'toast-container';
      el.className = 'toast-container';
      document.body.appendChild(el);
    }
    return el;
  }

  function toast(message, type = 'info') {
    const container = ensureToastContainer();
    const item = document.createElement('div');
    item.className = `toast ${type === 'error' ? 'error' : ''}`;
    item.innerHTML = `<span>${escapeHtml(message)}</span>`;
    container.appendChild(item);
    setTimeout(() => {
      item.remove();
    }, 4500);
  }

  function renderSidebar(activeId, user) {
    const sidebar = document.getElementById('app-sidebar');
    if (!sidebar) return;

    const navHtml = NAV_ITEMS.map((item) => {
      if (item.section) {
        return `<div class="nav-section-label">${escapeHtml(item.section)}</div>`;
      }
      const activeClass = item.id === activeId ? 'active' : '';
      return `
        <a href="${item.href}" class="nav-link ${activeClass}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${item.icon}</svg>
          <span>${escapeHtml(item.label)}</span>
        </a>`;
    }).join('');

    const displayName = user && user.full_name ? user.full_name : 'Analyst';
    const displayEmail = user && user.email ? user.email : 'Local Session';

    sidebar.innerHTML = `
      <div class="sidebar-brand">
        <a href="/frontend/dashboard.html" class="brand-mark">
          <span class="brand-accent"></span>
          <span>CommerceIQ</span>
        </a>
      </div>
      <nav class="sidebar-nav" aria-label="Primary Navigation">
        ${navHtml}
      </nav>
      <div class="sidebar-footer">
        <div class="user-summary">
          <span class="user-name">${escapeHtml(displayName)}</span>
          <span class="user-email">${escapeHtml(displayEmail)}</span>
        </div>
        <button type="button" class="btn-sidebar-logout" id="sidebar-logout-btn">Sign Out</button>
      </div>
    `;

    const logoutBtn = document.getElementById('sidebar-logout-btn');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', () => global.Auth.logout());
    }

    const menuBtn = document.getElementById('mobile-menu-btn');
    const backdrop = document.getElementById('sidebar-backdrop');
    if (menuBtn && backdrop) {
      menuBtn.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        backdrop.classList.toggle('open');
      });
      backdrop.addEventListener('click', () => {
        sidebar.classList.remove('open');
        backdrop.classList.remove('open');
      });
    }
  }

  async function initShell(activeId) {
    const user = await global.Auth.requireAuth();
    if (!user) return null;
    renderSidebar(activeId, user);
    return user;
  }

  function renderErrorBanner(container, message, onRetry) {
    if (!container) return;
    container.innerHTML = `
      <div class="notice-banner pink">
        <div>
          <p class="notice-title">Unable to load data</p>
          <p class="notice-body">${escapeHtml(message)}</p>
        </div>
        ${onRetry ? '<button type="button" class="btn btn-outline btn-sm" id="banner-retry-btn">Retry</button>' : ''}
      </div>`;
    if (onRetry) {
      const btn = container.querySelector('#banner-retry-btn');
      if (btn) btn.addEventListener('click', onRetry);
    }
  }

  function renderEmptyState(container, title, description, ctaLabel, ctaHref) {
    if (!container) return;
    container.innerHTML = `
      <div class="empty-state">
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(description)}</p>
        ${ctaLabel && ctaHref ? `<a href="${ctaHref}" class="btn btn-primary">${escapeHtml(ctaLabel)}</a>` : ''}
      </div>`;
  }

  global.UI = {
    escapeHtml,
    formatCurrency,
    formatNumber,
    formatDate,
    toast,
    initShell,
    renderErrorBanner,
    renderEmptyState,
  };
})(window);
