(function () {
  async function loadDashboard() {
    const alertSlot = document.getElementById('dashboard-alert-slot');
    const kpiGrid = document.getElementById('dashboard-kpis');
    const emptySlot = document.getElementById('dashboard-empty-slot');
    const chartsSection = document.getElementById('dashboard-charts-section');
    const tablesSection = document.getElementById('dashboard-tables-section');

    alertSlot.innerHTML = '';
    emptySlot.innerHTML = '';

    try {
      const [data, caps] = await Promise.all([
        window.API.get('/api/analytics/dashboard'),
        window.API.get('/api/analytics/data-capabilities'),
      ]);

      const s = data.summary || {};
      kpiGrid.innerHTML = `
        <div class="kpi-card">
          <span class="kpi-label">Total Revenue</span>
          <span class="kpi-value">${window.UI.formatCurrency(s.total_revenue || 0)}</span>
          <span class="kpi-sub">${window.UI.formatNumber(s.active_datasets || 0)} imported datasets</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Total Orders</span>
          <span class="kpi-value">${window.UI.formatNumber(s.total_orders || 0)}</span>
          <span class="kpi-sub">${window.UI.formatNumber(s.total_sales_rows || 0)} transaction lines</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Total Customers</span>
          <span class="kpi-value">${window.UI.formatNumber(s.total_customers || 0)}</span>
          <span class="kpi-sub">${caps.rfm.ready ? 'RFM clustering ready' : 'Needs dated orders for RFM'}</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Total Products</span>
          <span class="kpi-value">${window.UI.formatNumber(s.total_products || 0)}</span>
          <span class="kpi-sub">${caps.forecasting.ready ? 'Forecasting ready' : 'Needs >=3 periods history'}</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Average Order Value</span>
          <span class="kpi-value">${window.UI.formatCurrency(s.average_order_value || 0)}</span>
          <span class="kpi-sub accent">${s.date_range_label ? window.UI.escapeHtml(s.date_range_label) : 'No dated transactions'}</span>
        </div>
      `;

      const hasAnyData =
        (s.total_orders || 0) > 0 ||
        (s.total_sales_rows || 0) > 0 ||
        (s.total_customers || 0) > 0 ||
        (s.total_products || 0) > 0;

      if (!hasAnyData) {
        chartsSection.style.display = 'none';
        tablesSection.style.display = 'none';
        window.UI.renderEmptyState(
          emptySlot,
          'No e-commerce CSV data imported yet',
          'Upload your existing products, customers, orders, sales, transactions, or inventory CSV files to populate live revenue metrics, charts, RFM cohorts, and demand forecasts.',
          'Upload First CSV',
          '/frontend/csv-upload.html'
        );
        return;
      }

      // Surface capability gaps honestly if some datasets are uploaded while others are missing
      const warnings = [];
      if (!caps.rfm.ready) warnings.push(`RFM Segmentation: ${caps.rfm.reason}`);
      if (!caps.forecasting.ready) warnings.push(`Demand Forecasting: ${caps.forecasting.reason}`);
      if (!caps.inventory_alerts.ready) warnings.push(`Low-Stock Alerts: ${caps.inventory_alerts.reason}`);

      if (warnings.length > 0) {
        alertSlot.innerHTML = `
          <div class="notice-banner">
            <div>
              <p class="notice-title">Partial Dataset Coverage</p>
              <p class="notice-body">${warnings.map(window.UI.escapeHtml).join(' · ')}</p>
            </div>
            <a href="/frontend/csv-upload.html" class="btn btn-outline btn-sm">Add Dataset</a>
          </div>`;
      }

      chartsSection.style.display = 'grid';
      tablesSection.style.display = 'grid';

      // Monthly Trend Chart
      const monthly = data.monthly_sales || [];
      if (monthly.length > 0) {
        window.Charts.renderLineOrBar('dashboard-trend-chart', {
          type: 'line',
          data: {
            labels: monthly.map((m) => m.period),
            datasets: [
              {
                label: 'Revenue ($)',
                data: monthly.map((m) => m.revenue),
                borderColor: window.Charts.COLORS.PINK,
                backgroundColor: window.Charts.COLORS.PINK_16,
                fill: true,
                tension: 0.25,
                borderWidth: 2.5,
                yAxisID: 'y',
              },
              {
                label: 'Orders',
                data: monthly.map((m) => m.orders),
                borderColor: window.Charts.COLORS.NAVY,
                backgroundColor: 'transparent',
                tension: 0.25,
                borderWidth: 2,
                borderDash: [4, 4],
                yAxisID: 'y1',
              },
            ],
          },
          options: {
            scales: {
              x: { grid: { display: false }, ticks: { color: window.Charts.COLORS.NAVY_70 } },
              y: {
                type: 'linear',
                position: 'left',
                grid: { color: window.Charts.COLORS.NAVY_08 },
                ticks: { color: window.Charts.COLORS.NAVY_70 },
              },
              y1: {
                type: 'linear',
                position: 'right',
                grid: { drawOnChartArea: false },
                ticks: { color: window.Charts.COLORS.NAVY_70 },
              },
            },
          },
        });
      }

      // Category Performance Chart
      const categories = data.category_performance || [];
      if (categories.length > 0) {
        window.Charts.renderDoughnut(
          'dashboard-category-chart',
          categories.slice(0, 6).map((c) => c.category),
          categories.slice(0, 6).map((c) => c.revenue)
        );
      }

      // Top Products Table
      const topProductsBody = document.getElementById('top-products-tbody');
      const topProducts = data.top_products || [];
      topProductsBody.innerHTML =
        topProducts.length === 0
          ? '<tr><td colspan="4" style="text-align:center; color: var(--navy-52);">No product revenue records available.</td></tr>'
          : topProducts
              .map(
                (p) => `
          <tr>
            <td><strong>${window.UI.escapeHtml(p.name)}</strong></td>
            <td>${window.UI.escapeHtml(p.category || 'Uncategorized')}</td>
            <td class="num">${window.UI.formatNumber(p.units_sold)}</td>
            <td class="num">${window.UI.formatCurrency(p.revenue)}</td>
          </tr>`
              )
              .join('');

      // Recent Transactions Table
      const recentBody = document.getElementById('recent-txns-tbody');
      const recentTxns = data.recent_transactions || [];
      recentBody.innerHTML =
        recentTxns.length === 0
          ? '<tr><td colspan="4" style="text-align:center; color: var(--navy-52);">No dated transactions imported yet.</td></tr>'
          : recentTxns
              .map(
                (t) => `
          <tr>
            <td class="mono">${window.UI.escapeHtml(t.reference)}</td>
            <td>${window.UI.formatDate(t.date)}</td>
            <td>${window.UI.escapeHtml(t.customer || 'Guest / Unmapped')}</td>
            <td class="num">${window.UI.formatCurrency(t.amount)}</td>
          </tr>`
              )
              .join('');
    } catch (err) {
      window.UI.renderErrorBanner(alertSlot, err.message, loadDashboard);
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const user = await window.UI.initShell('dashboard');
    if (!user) return;
    document.getElementById('refresh-dashboard-btn').addEventListener('click', loadDashboard);
    await loadDashboard();
  });
})();
