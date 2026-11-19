(function () {
  let cachedAlerts = [];

  function renderFilteredAlerts() {
    const category = document.getElementById('alerts-category-filter').value;
    const listEl = document.getElementById('alerts-list');
    const emptySlot = document.getElementById('alerts-empty-slot');

    const items = category ? cachedAlerts.filter((a) => a.category === category) : cachedAlerts;
    if (items.length === 0) {
      listEl.innerHTML = '';
      window.UI.renderEmptyState(
        emptySlot,
        'No alerts triggered for current filter',
        'Smart alerts only fire when imported SQLite records cross statistical thresholds (trend shifts, z-score anomalies, at-risk RFM cohorts, or low inventory).',
        'Upload CSV Data',
        '/frontend/csv-upload.html'
      );
      return;
    }

    emptySlot.innerHTML = '';
    listEl.innerHTML = items
      .map(
        (a) => `
      <article class="card">
        <div class="card-header">
          <div>
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 4px;">
              <span class="status-label ${a.severity === 'critical' || a.severity === 'warning' ? 'pink' : 'navy-solid'}">${window.UI.escapeHtml(a.severity.toUpperCase())}</span>
              <span style="font-size: 12px; color: var(--navy-52); font-weight: 600;">${window.UI.escapeHtml(a.category_label)}</span>
            </div>
            <h2 class="card-title">${window.UI.escapeHtml(a.title)}</h2>
          </div>
          ${a.metric_value ? `<span class="mono" style="font-weight: 700; color: var(--navy);">${window.UI.escapeHtml(a.metric_value)}</span>` : ''}
        </div>
        <p style="margin: 0; color: var(--navy-72); font-size: 13.5px;">${window.UI.escapeHtml(a.description)}</p>
        <div style="padding-top: 10px; border-top: 1px solid var(--navy-07); font-size: 13px;">
          <strong>Recommended Action:</strong> ${window.UI.escapeHtml(a.recommendation)}
        </div>
      </article>`
      )
      .join('');
  }

  async function loadAlerts() {
    const bannerSlot = document.getElementById('alerts-slot-banner');
    const kpiSlot = document.getElementById('alerts-kpis');
    bannerSlot.innerHTML = '';

    try {
      const data = await window.API.get('/api/insights/alerts');
      cachedAlerts = data.alerts || [];

      const counts = data.summary || {};
      kpiSlot.innerHTML = `
        <div class="kpi-card"><span class="kpi-label">Total Active Insights</span><span class="kpi-value">${window.UI.formatNumber(counts.total || 0)}</span><span class="kpi-sub">Data-verified rules</span></div>
        <div class="kpi-card"><span class="kpi-label">Critical / Warnings</span><span class="kpi-value">${window.UI.formatNumber(counts.critical_and_warning || 0)}</span><span class="kpi-sub accent">Require attention</span></div>
        <div class="kpi-card"><span class="kpi-label">Growth Opportunities</span><span class="kpi-value">${window.UI.formatNumber(counts.opportunities || 0)}</span><span class="kpi-sub">Top products &amp; surges</span></div>
        <div class="kpi-card"><span class="kpi-label">Unsupported Detectors</span><span class="kpi-value">${window.UI.formatNumber((data.skipped_detectors || []).length)}</span><span class="kpi-sub">Missing required columns</span></div>
      `;

      if (data.skipped_detectors && data.skipped_detectors.length > 0) {
        bannerSlot.innerHTML = `
          <div class="notice-banner">
            <div>
              <p class="notice-title">Detectors Waiting for Required CSV Columns</p>
              <p class="notice-body">${data.skipped_detectors.map(window.UI.escapeHtml).join(' · ')}</p>
            </div>
          </div>`;
      }

      renderFilteredAlerts();
    } catch (err) {
      window.UI.renderErrorBanner(bannerSlot, err.message, loadAlerts);
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const user = await window.UI.initShell('alerts');
    if (!user) return;
    document.getElementById('alerts-category-filter').addEventListener('change', renderFilteredAlerts);
    document.getElementById('btn-refresh-alerts').addEventListener('click', loadAlerts);
    await loadAlerts();
  });
})();
