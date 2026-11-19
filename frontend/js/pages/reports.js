(function () {
  async function loadReportReadiness() {
    const alertSlot = document.getElementById('reports-alert-slot');
    alertSlot.innerHTML = '';
    try {
      const caps = await window.API.get('/api/analytics/data-capabilities');
      const map = {
        sales: caps.sales,
        segmentation: caps.rfm,
        product_performance: caps.sales,
        forecasts: caps.forecasting,
        recommendations: caps.insights,
      };
      Object.entries(map).forEach(([key, state]) => {
        const badge = document.getElementById(`rep-status-${key}`);
        const note = document.getElementById(`rep-note-${key}`);
        if (!badge || !note || !state) return;
        badge.textContent = state.ready ? 'Ready' : 'Needs Data';
        badge.className = `status-label ${state.ready ? 'navy-solid' : 'pink'}`;
        note.textContent = state.reason || '';

        document.querySelectorAll(`.btn-download-report[data-type="${key}"]`).forEach((btn) => {
          btn.disabled = !state.ready;
        });
      });
    } catch (err) {
      window.UI.renderErrorBanner(alertSlot, err.message, loadReportReadiness);
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const user = await window.UI.initShell('reports');
    if (!user) return;

    document.getElementById('btn-refresh-reports').addEventListener('click', loadReportReadiness);

    document.querySelectorAll('.btn-download-report').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const reportType = btn.dataset.type;
        const fmt = btn.dataset.format;
        const origText = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Generating...';
        try {
          await window.API.downloadFile(
            `/api/reports/${fmt}/${reportType}`,
            `commerceiq_${reportType}.${fmt}`
          );
          window.UI.toast(`Downloaded ${reportType} (${fmt.toUpperCase()}).`);
        } catch (err) {
          window.UI.toast(err.message, 'error');
        } finally {
          btn.disabled = false;
          btn.textContent = origText;
        }
      });
    });

    await loadReportReadiness();
  });
})();
