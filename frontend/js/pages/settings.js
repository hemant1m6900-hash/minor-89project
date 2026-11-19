(function () {
  async function loadSettings(user) {
    const alertSlot = document.getElementById('settings-alert-slot');
    alertSlot.innerHTML = '';
    document.getElementById('set-account-email').value = user.email || '';

    try {
      const data = await window.API.get('/api/settings');
      const cfg = data.thresholds || {};
      document.getElementById('set-low-stock').value = cfg.low_stock_threshold ?? 10;
      document.getElementById('set-at-risk-days').value = cfg.at_risk_days ?? 60;
      document.getElementById('set-rfm-clusters').value = String(cfg.rfm_clusters ?? 5);
      document.getElementById('set-forecast-horizon').value = cfg.forecast_horizon ?? 4;
      document.getElementById('set-anomaly-z').value = cfg.anomaly_z_threshold ?? 2.0;

      const sys = data.system || {};
      document.getElementById('system-info-grid').innerHTML = `
        <div class="kpi-card">
          <span class="kpi-label">Database Engine</span>
          <span class="kpi-value" style="font-size: 18px;">${window.UI.escapeHtml(sys.database_dialect || 'SQLite (ecommerce_intelligence.db)')}</span>
          <span class="kpi-sub">${sys.database_connected ? 'Connection verified' : 'Check connection'}</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">API Base URL</span>
          <span class="kpi-value mono" style="font-size: 14px; word-break: break-all;">${window.UI.escapeHtml(window.API.getApiBase() || window.location.origin)}</span>
          <span class="kpi-sub">Fetch API target</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Local Upload Storage</span>
          <span class="kpi-value mono" style="font-size: 14px;">${window.UI.escapeHtml(sys.upload_dir || 'storage/uploads')}</span>
          <span class="kpi-sub">Original CSV preservation path</span>
        </div>
      `;
    } catch (err) {
      window.UI.renderErrorBanner(alertSlot, err.message, () => loadSettings(user));
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const user = await window.UI.initShell('settings');
    if (!user) return;

    document.getElementById('thresholds-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        await window.API.put('/api/settings', {
          low_stock_threshold: Number(document.getElementById('set-low-stock').value),
          at_risk_days: Number(document.getElementById('set-at-risk-days').value),
          rfm_clusters: Number(document.getElementById('set-rfm-clusters').value),
          forecast_horizon: Number(document.getElementById('set-forecast-horizon').value),
          anomaly_z_threshold: Number(document.getElementById('set-anomaly-z').value),
        });
        window.UI.toast('Analytics settings saved to SQLite.');
      } catch (err) {
        window.UI.toast(err.message, 'error');
      }
    });

    document.getElementById('password-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        await window.API.put('/api/auth/password', {
          current_password: document.getElementById('set-current-pw').value,
          new_password: document.getElementById('set-new-pw').value,
        });
        document.getElementById('set-current-pw').value = '';
        document.getElementById('set-new-pw').value = '';
        window.UI.toast('Password updated.');
      } catch (err) {
        window.UI.toast(err.message, 'error');
      }
    });

    await loadSettings(user);
  });
})();
