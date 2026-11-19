(function () {
  async function loadSalesAnalytics() {
    const alertSlot = document.getElementById('sales-alert-slot');
    const emptySlot = document.getElementById('sales-empty-slot');
    const content = document.getElementById('sales-content');
    alertSlot.innerHTML = '';
    emptySlot.innerHTML = '';

    const params = new URLSearchParams();
    const start = document.getElementById('sales-start-date').value;
    const end = document.getElementById('sales-end-date').value;
    const category = document.getElementById('sales-category').value;
    const granularity = document.getElementById('sales-granularity').value;

    if (start) params.set('start_date', start);
    if (end) params.set('end_date', end);
    if (category) params.set('category', category);
    params.set('granularity', granularity);

    try {
      const data = await window.API.get(`/api/analytics/sales?${params.toString()}`);

      // Populate category filter options while preserving selection
      const catSelect = document.getElementById('sales-category');
      const existingCats = data.available_categories || [];
      if (catSelect.options.length <= 1 && existingCats.length > 0) {
        existingCats.forEach((c) => {
          const opt = document.createElement('option');
          opt.value = c;
          opt.textContent = c;
          catSelect.appendChild(opt);
        });
        if (category) catSelect.value = category;
      }

      const s = data.summary || {};
      if ((s.total_orders || 0) === 0 && (s.total_revenue || 0) === 0) {
        content.style.display = 'none';
        window.UI.renderEmptyState(
          emptySlot,
          'No matching sales data found',
          'Either no sales/orders CSV has been imported yet, or your active date/category filters exclude all transactions.',
          'Upload Sales / Orders CSV',
          '/frontend/csv-upload.html'
        );
        return;
      }

      content.style.display = 'flex';
      document.getElementById('sales-kpis').innerHTML = `
        <div class="kpi-card">
          <span class="kpi-label">Filtered Revenue</span>
          <span class="kpi-value">${window.UI.formatCurrency(s.total_revenue)}</span>
          <span class="kpi-sub">Realized total</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Filtered Orders</span>
          <span class="kpi-value">${window.UI.formatNumber(s.total_orders)}</span>
          <span class="kpi-sub">${window.UI.formatNumber(s.total_units)} total units</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Average Order Value</span>
          <span class="kpi-value">${window.UI.formatCurrency(s.average_order_value)}</span>
          <span class="kpi-sub">Revenue per order</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Period Growth</span>
          <span class="kpi-value">${s.growth_pct !== null && s.growth_pct !== undefined ? `${s.growth_pct > 0 ? '+' : ''}${s.growth_pct}%` : '—'}</span>
          <span class="kpi-sub accent">Latest vs prior period</span>
        </div>
      `;

      const trend = data.trend || [];
      window.Charts.renderLineOrBar('sales-trend-chart', {
        type: 'bar',
        data: {
          labels: trend.map((t) => t.period),
          datasets: [
            {
              label: 'Revenue ($)',
              data: trend.map((t) => t.revenue),
              backgroundColor: window.Charts.COLORS.PINK,
              borderRadius: 4,
            },
          ],
        },
      });

      const cats = data.categories || [];
      window.Charts.renderLineOrBar('sales-category-chart', {
        type: 'bar',
        data: {
          labels: cats.slice(0, 8).map((c) => c.category),
          datasets: [
            {
              label: 'Category Revenue ($)',
              data: cats.slice(0, 8).map((c) => c.revenue),
              backgroundColor: window.Charts.COLORS.NAVY,
              borderRadius: 4,
            },
          ],
        },
        options: { indexAxis: 'y' },
      });

      const prodBody = document.getElementById('sales-products-tbody');
      prodBody.innerHTML = (data.top_products || [])
        .map(
          (p) => `
        <tr>
          <td><strong>${window.UI.escapeHtml(p.name)}</strong></td>
          <td class="mono">${window.UI.escapeHtml(p.sku || '—')}</td>
          <td>${window.UI.escapeHtml(p.category || 'Uncategorized')}</td>
          <td class="num">${window.UI.formatNumber(p.units_sold)}</td>
          <td class="num">${window.UI.formatCurrency(p.avg_price)}</td>
          <td class="num">${window.UI.formatCurrency(p.revenue)}</td>
        </tr>`
        )
        .join('') || '<tr><td colspan="6" style="text-align:center;">No product breakdown available.</td></tr>';

      const ordBody = document.getElementById('sales-orders-tbody');
      ordBody.innerHTML = (data.transactions || [])
        .map(
          (o) => `
        <tr>
          <td class="mono">${window.UI.escapeHtml(o.reference)}</td>
          <td>${window.UI.formatDate(o.date)}</td>
          <td>${window.UI.escapeHtml(o.customer || '—')}</td>
          <td>${window.UI.escapeHtml(o.payment_method || '—')}</td>
          <td><span class="status-label">${window.UI.escapeHtml(o.status || 'completed')}</span></td>
          <td class="num">${window.UI.formatCurrency(o.amount)}</td>
        </tr>`
        )
        .join('') || '<tr><td colspan="6" style="text-align:center;">No transactions found.</td></tr>';
    } catch (err) {
      window.UI.renderErrorBanner(alertSlot, err.message, loadSalesAnalytics);
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const user = await window.UI.initShell('sales');
    if (!user) return;

    document.getElementById('sales-filter-form').addEventListener('submit', (e) => {
      e.preventDefault();
      loadSalesAnalytics();
    });
    document.getElementById('sales-reset-btn').addEventListener('click', () => {
      document.getElementById('sales-start-date').value = '';
      document.getElementById('sales-end-date').value = '';
      document.getElementById('sales-category').value = '';
      document.getElementById('sales-granularity').value = 'monthly';
      loadSalesAnalytics();
    });

    await loadSalesAnalytics();
  });
})();
