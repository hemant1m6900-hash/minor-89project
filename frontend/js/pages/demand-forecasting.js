(function () {
  async function loadForecastProducts() {
    const select = document.getElementById('forecast-product-select');
    try {
      const data = await window.API.get('/api/forecasting/products');
      const current = select.value;
      select.innerHTML = '<option value="">All Eligible Products (Aggregate)</option>';
      (data.products || []).forEach((p) => {
        const opt = document.createElement('option');
        opt.value = String(p.id);
        opt.textContent = `${p.name} (${p.periods_count} periods)`;
        select.appendChild(opt);
      });
      if (current) select.value = current;
    } catch {
      // Handled by main forecast call
    }
  }

  async function runForecast() {
    const alertSlot = document.getElementById('forecast-alert-slot');
    const emptySlot = document.getElementById('forecast-empty-slot');
    const content = document.getElementById('forecast-content');
    const btn = document.getElementById('btn-run-forecast');

    alertSlot.innerHTML = '';
    emptySlot.innerHTML = '';
    btn.disabled = true;
    btn.textContent = 'Computing...';

    const productId = document.getElementById('forecast-product-select').value;
    const granularity = document.getElementById('forecast-granularity').value;
    const horizon = Number(document.getElementById('forecast-horizon').value || 4);

    try {
      const data = await window.API.post('/api/forecasting/run', {
        product_id: productId ? Number(productId) : null,
        granularity,
        horizon,
      });

      if (!data.sufficient_data) {
        content.style.display = 'none';
        window.UI.renderEmptyState(
          emptySlot,
          'Insufficient historical demand periods',
          data.message || 'At least 3 historical time periods of product sales are required for baseline forecasting, and 6+ periods for Scikit-learn regression.',
          'Upload Historical Sales CSV',
          '/frontend/csv-upload.html'
        );
        return;
      }

      content.style.display = 'flex';
      const m = data.metrics || {};

      document.getElementById('forecast-kpis').innerHTML = `
        <div class="kpi-card">
          <span class="kpi-label">Active Model</span>
          <span class="kpi-value" style="font-size: 18px;">${window.UI.escapeHtml(data.model_name)}</span>
          <span class="kpi-sub">${data.ml_trained ? 'Scikit-learn trained on holdout' : 'Baseline only (<6 periods)'}</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Validation MAE</span>
          <span class="kpi-value">${m.mae !== null && m.mae !== undefined ? Number(m.mae).toFixed(2) : 'N/A'}</span>
          <span class="kpi-sub">Units mean absolute error</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Validation RMSE</span>
          <span class="kpi-value">${m.rmse !== null && m.rmse !== undefined ? Number(m.rmse).toFixed(2) : 'N/A'}</span>
          <span class="kpi-sub">Root mean squared error</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Historical Periods</span>
          <span class="kpi-value">${window.UI.formatNumber(data.history_periods)}</span>
          <span class="kpi-sub accent">Next period forecast: ${window.UI.formatNumber(data.next_period_forecast, 1)} units</span>
        </div>
      `;

      document.getElementById('forecast-model-badge').textContent = data.ml_trained ? 'SCIKIT-LEARN ML' : 'BASELINE';
      document.getElementById('forecast-chart-sub').textContent =
        `${data.target_label} · ${data.explanation}`;

      const series = data.series || [];
      const labels = series.map((pt) => pt.period);
      const actuals = series.map((pt) => pt.actual);
      const predicted = series.map((pt) => pt.predicted);

      window.Charts.renderLineOrBar('forecast-chart', {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Actual Units Sold',
              data: actuals,
              borderColor: window.Charts.COLORS.NAVY,
              backgroundColor: 'transparent',
              borderWidth: 2.5,
              tension: 0.2,
              spanGaps: false,
            },
            {
              label: 'Predicted / Forecast Units',
              data: predicted,
              borderColor: window.Charts.COLORS.PINK,
              backgroundColor: window.Charts.COLORS.PINK_16,
              borderDash: [5, 4],
              borderWidth: 2.5,
              tension: 0.2,
              fill: true,
              spanGaps: true,
            },
          ],
        },
      });

      const futureRows = data.future_forecasts || [];
      document.getElementById('forecast-future-tbody').innerHTML = futureRows
        .map(
          (f) => `
        <tr>
          <td class="mono">${window.UI.escapeHtml(f.period)}</td>
          <td class="num"><strong>${window.UI.formatNumber(f.predicted, 1)}</strong></td>
          <td><span class="status-label">${window.UI.escapeHtml(f.method)}</span></td>
        </tr>`
        )
        .join('') || '<tr><td colspan="3" style="text-align:center;">No future periods generated.</td></tr>';

      const prodSummaries = data.product_summaries || [];
      const prodTbody = document.getElementById('forecast-products-tbody');
      prodTbody.innerHTML = prodSummaries
        .map(
          (p) => `
        <tr class="forecast-product-row" data-id="${p.product_id}" style="cursor: pointer;">
          <td><strong>${window.UI.escapeHtml(p.product_name)}</strong></td>
          <td class="num">${window.UI.formatNumber(p.history_periods)}</td>
          <td><span class="status-label ${p.ml_trained ? 'navy-solid' : ''}">${window.UI.escapeHtml(p.model_name)}</span></td>
          <td class="num">${p.next_period_forecast !== null ? window.UI.formatNumber(p.next_period_forecast, 1) : '—'}</td>
          <td class="num">${p.mae !== null && p.mae !== undefined ? Number(p.mae).toFixed(2) : '—'}</td>
        </tr>`
        )
        .join('') || '<tr><td colspan="5" style="text-align:center;">No per-product summaries.</td></tr>';

      prodTbody.querySelectorAll('.forecast-product-row').forEach((row) => {
        row.addEventListener('click', () => {
          document.getElementById('forecast-product-select').value = row.dataset.id;
          runForecast();
        });
      });
    } catch (err) {
      window.UI.renderErrorBanner(alertSlot, err.message, runForecast);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Generate Forecast';
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const user = await window.UI.initShell('forecasting');
    if (!user) return;
    document.getElementById('forecast-controls-form').addEventListener('submit', (e) => {
      e.preventDefault();
      runForecast();
    });
    await loadForecastProducts();
    await runForecast();
  });
})();
