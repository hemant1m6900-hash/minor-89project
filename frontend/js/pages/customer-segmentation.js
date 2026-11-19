(function () {
  let allCustomers = [];

  function renderCustomerTable() {
    const segFilter = document.getElementById('rfm-filter-segment').value;
    const query = document.getElementById('rfm-search-input').value.trim().toLowerCase();
    const tbody = document.getElementById('rfm-customers-tbody');

    const filtered = allCustomers.filter((c) => {
      if (segFilter && c.segment !== segFilter) return false;
      if (query) {
        const hay = `${c.name || ''} ${c.email || ''} ${c.external_id || ''}`.toLowerCase();
        if (!hay.includes(query)) return false;
      }
      return true;
    });

    tbody.innerHTML =
      filtered
        .slice(0, 150)
        .map(
          (c) => `
      <tr>
        <td><strong>${window.UI.escapeHtml(c.name || c.external_id)}</strong></td>
        <td class="mono" style="font-size: 12px;">${window.UI.escapeHtml(c.email || c.external_id)}</td>
        <td><span class="status-label ${c.segment === 'Champions' || c.segment === 'At-Risk' ? 'pink' : ''}">${window.UI.escapeHtml(c.segment)}</span></td>
        <td class="num">${window.UI.formatNumber(c.recency)}</td>
        <td class="num">${window.UI.formatNumber(c.frequency)}</td>
        <td class="num">${window.UI.formatCurrency(c.monetary)}</td>
      </tr>`
        )
        .join('') || '<tr><td colspan="6" style="text-align:center;">No matching customers.</td></tr>';
  }

  function renderRFMResult(data) {
    const emptySlot = document.getElementById('rfm-empty-slot');
    const content = document.getElementById('rfm-content');

    if (!data || !data.sufficient_data) {
      content.style.display = 'none';
      window.UI.renderEmptyState(
        emptySlot,
        'Insufficient data for K-Means RFM Segmentation',
        (data && data.message) ||
          'Upload an orders or sales CSV containing at least 5 distinct customers with valid transaction dates and monetary amounts.',
        'Upload Orders / Sales CSV',
        '/frontend/csv-upload.html'
      );
      return;
    }

    emptySlot.innerHTML = '';
    content.style.display = 'flex';

    document.getElementById('rfm-kpis').innerHTML = `
      <div class="kpi-card">
        <span class="kpi-label">Segmented Customers</span>
        <span class="kpi-value">${window.UI.formatNumber(data.total_customers)}</span>
        <span class="kpi-sub">Active clusters: ${data.n_clusters}</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Total Cohort Revenue</span>
        <span class="kpi-value">${window.UI.formatCurrency(data.total_revenue)}</span>
        <span class="kpi-sub">Reference date: ${window.UI.formatDate(data.reference_date)}</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Silhouette Score</span>
        <span class="kpi-value">${data.silhouette_score !== null && data.silhouette_score !== undefined ? Number(data.silhouette_score).toFixed(3) : 'N/A'}</span>
        <span class="kpi-sub accent">Scikit-learn K-Means quality</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Top Segment</span>
        <span class="kpi-value" style="font-size: 20px;">${window.UI.escapeHtml((data.segments[0] && data.segments[0].segment) || '—')}</span>
        <span class="kpi-sub">${data.segments[0] ? window.UI.formatCurrency(data.segments[0].total_revenue) : ''}</span>
      </div>
    `;

    const segs = data.segments || [];
    window.Charts.renderLineOrBar('rfm-segment-bar-chart', {
      type: 'bar',
      data: {
        labels: segs.map((s) => s.segment),
        datasets: [
          {
            label: 'Total Revenue ($)',
            data: segs.map((s) => s.total_revenue),
            backgroundColor: window.Charts.COLORS.PINK,
            borderRadius: 4,
            yAxisID: 'y',
          },
          {
            label: 'Customers',
            data: segs.map((s) => s.customer_count),
            backgroundColor: window.Charts.COLORS.NAVY,
            borderRadius: 4,
            yAxisID: 'y1',
          },
        ],
      },
      options: {
        scales: {
          x: { grid: { display: false }, ticks: { color: window.Charts.COLORS.NAVY_70 } },
          y: { type: 'linear', position: 'left', grid: { color: window.Charts.COLORS.NAVY_08 } },
          y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false } },
        },
      },
    });

    allCustomers = data.customers || [];
    const scatterPointsTop = allCustomers
      .filter((c) => c.segment === 'Champions' || c.segment === 'Loyal')
      .slice(0, 200)
      .map((c) => ({ x: c.recency, y: c.monetary }));
    const scatterPointsOther = allCustomers
      .filter((c) => c.segment !== 'Champions' && c.segment !== 'Loyal')
      .slice(0, 200)
      .map((c) => ({ x: c.recency, y: c.monetary }));

    window.Charts.renderLineOrBar('rfm-scatter-chart', {
      type: 'scatter',
      data: {
        datasets: [
          {
            label: 'Champions & Loyal',
            data: scatterPointsTop,
            backgroundColor: window.Charts.COLORS.PINK,
            pointRadius: 5,
          },
          {
            label: 'Other Segments',
            data: scatterPointsOther,
            backgroundColor: window.Charts.COLORS.NAVY,
            pointRadius: 4,
          },
        ],
      },
      options: {
        scales: {
          x: { title: { display: true, text: 'Recency (Days)', color: window.Charts.COLORS.NAVY }, grid: { color: window.Charts.COLORS.NAVY_08 } },
          y: { title: { display: true, text: 'Monetary ($)', color: window.Charts.COLORS.NAVY }, grid: { color: window.Charts.COLORS.NAVY_08 } },
        },
      },
    });

    document.getElementById('rfm-segments-tbody').innerHTML = segs
      .map(
        (s) => `
      <tr>
        <td><strong>${window.UI.escapeHtml(s.segment)}</strong></td>
        <td class="num">${window.UI.formatNumber(s.customer_count)}</td>
        <td class="num">${window.UI.formatCurrency(s.total_revenue)}</td>
        <td class="num">${s.revenue_share_pct}%</td>
        <td class="num">${Number(s.avg_recency).toFixed(1)}</td>
        <td class="num">${Number(s.avg_frequency).toFixed(1)}</td>
        <td class="num">${window.UI.formatCurrency(s.avg_monetary)}</td>
      </tr>`
      )
      .join('');

    const filterSel = document.getElementById('rfm-filter-segment');
    filterSel.innerHTML = '<option value="">All Segments</option>';
    segs.forEach((s) => {
      const opt = document.createElement('option');
      opt.value = s.segment;
      opt.textContent = s.segment;
      filterSel.appendChild(opt);
    });

    renderCustomerTable();
  }

  async function runRFM(forceRun = false) {
    const alertSlot = document.getElementById('rfm-alert-slot');
    const btn = document.getElementById('btn-run-rfm');
    alertSlot.innerHTML = '';
    const k = Number(document.getElementById('rfm-clusters-select').value || 5);
    btn.disabled = true;
    btn.textContent = 'Running K-Means...';
    try {
      const data = forceRun
        ? await window.API.post('/api/segmentation/rfm', { n_clusters: k })
        : await window.API.get(`/api/segmentation/rfm?n_clusters=${k}`);
      renderRFMResult(data);
      if (forceRun && data.sufficient_data) {
        window.UI.toast('K-Means RFM segmentation updated.');
      }
    } catch (err) {
      window.UI.renderErrorBanner(alertSlot, err.message, () => runRFM(forceRun));
    } finally {
      btn.disabled = false;
      btn.textContent = 'Run K-Means RFM';
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const user = await window.UI.initShell('segmentation');
    if (!user) return;
    document.getElementById('btn-run-rfm').addEventListener('click', () => runRFM(true));
    document.getElementById('rfm-filter-segment').addEventListener('change', renderCustomerTable);
    document.getElementById('rfm-search-input').addEventListener('input', renderCustomerTable);
    await runRFM(false);
  });
})();
