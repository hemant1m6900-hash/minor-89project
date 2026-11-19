(function () {
  async function loadDataManagement() {
    const alertSlot = document.getElementById('dm-alert-slot');
    const capsGrid = document.getElementById('capabilities-grid');
    const tableSlot = document.getElementById('dm-table-slot');
    alertSlot.innerHTML = '';

    try {
      const [datasets, caps] = await Promise.all([
        window.API.get('/api/datasets'),
        window.API.get('/api/analytics/data-capabilities'),
      ]);

      const capEntries = [
        { title: 'Sales & Revenue', state: caps.sales },
        { title: 'RFM Segmentation', state: caps.rfm },
        { title: 'Demand Forecasting', state: caps.forecasting },
        { title: 'Inventory Alerts', state: caps.inventory_alerts },
      ];

      capsGrid.innerHTML = capEntries
        .map(
          (c) => `
        <div class="kpi-card">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span class="kpi-label">${window.UI.escapeHtml(c.title)}</span>
            <span class="status-label ${c.state.ready ? 'navy-solid' : 'pink'}">${c.state.ready ? 'Ready' : 'Missing Data'}</span>
          </div>
          <span class="kpi-sub" style="margin-top: 6px;">${window.UI.escapeHtml(c.state.reason)}</span>
        </div>`
        )
        .join('');

      if (!datasets || datasets.length === 0) {
        window.UI.renderEmptyState(
          tableSlot,
          'No datasets uploaded yet',
          'Upload your first CSV file to inspect its schema, clean missing values, and store normalized records in SQLite.',
          'Upload CSV',
          '/frontend/csv-upload.html'
        );
        return;
      }

      tableSlot.innerHTML = `
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Dataset Name</th>
                <th>Original File</th>
                <th>Type</th>
                <th>Status</th>
                <th class="num">Parsed</th>
                <th class="num">Imported</th>
                <th class="num">Skipped</th>
                <th>Uploaded</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${datasets
                .map(
                  (d) => `
                <tr>
                  <td><strong>${window.UI.escapeHtml(d.name)}</strong></td>
                  <td class="mono" style="font-size: 12px;">${window.UI.escapeHtml(d.original_filename)}</td>
                  <td style="text-transform: capitalize;">${window.UI.escapeHtml(d.dataset_type)}</td>
                  <td><span class="status-label ${d.import_status === 'imported' ? 'navy-solid' : d.import_status === 'failed' ? 'pink' : ''}">${window.UI.escapeHtml(d.import_status)}</span></td>
                  <td class="num">${window.UI.formatNumber(d.rows_parsed || 0)}</td>
                  <td class="num">${window.UI.formatNumber(d.rows_imported || 0)}</td>
                  <td class="num">${window.UI.formatNumber(d.rows_skipped || 0)}</td>
                  <td>${window.UI.formatDate(d.created_at)}</td>
                  <td>
                    <div style="display: flex; gap: 6px;">
                      <button type="button" class="btn btn-outline btn-sm btn-inspect" data-id="${d.id}">Inspect</button>
                      <a href="/frontend/csv-upload.html?reimport=${d.id}" class="btn btn-outline btn-sm">Re-Import</a>
                      <button type="button" class="btn btn-danger-outline btn-sm btn-delete" data-id="${d.id}" data-name="${window.UI.escapeHtml(d.name)}">Delete</button>
                    </div>
                  </td>
                </tr>`
                )
                .join('')}
            </tbody>
          </table>
        </div>`;

      tableSlot.querySelectorAll('.btn-inspect').forEach((btn) => {
        btn.addEventListener('click', () => inspectDataset(btn.dataset.id));
      });
      tableSlot.querySelectorAll('.btn-delete').forEach((btn) => {
        btn.addEventListener('click', () => deleteDataset(btn.dataset.id, btn.dataset.name));
      });
    } catch (err) {
      window.UI.renderErrorBanner(alertSlot, err.message, loadDataManagement);
    }
  }

  async function inspectDataset(id) {
    const modal = document.getElementById('dataset-detail-modal');
    const title = document.getElementById('modal-dataset-title');
    const sub = document.getElementById('modal-dataset-sub');
    const body = document.getElementById('modal-dataset-body');
    body.innerHTML = '<div class="skeleton" style="height: 120px;"></div>';
    modal.classList.add('open');

    try {
      const detail = await window.API.get(`/api/datasets/${id}`);
      title.textContent = detail.name;
      sub.textContent = `${detail.original_filename} · SHA-256: ${(detail.file_hash || '').slice(0, 16)}... · Local File: ${detail.stored_path || 'N/A'}`;
      const cols = detail.columns || [];
      const mapping = detail.column_mapping || {};
      body.innerHTML = `
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>CSV Column</th>
                <th>Detected Type</th>
                <th class="num">Missing</th>
                <th>Mapped Field</th>
              </tr>
            </thead>
            <tbody>
              ${cols
                .map(
                  (c) => `
                <tr>
                  <td><strong>${window.UI.escapeHtml(c.name)}</strong></td>
                  <td>${window.UI.escapeHtml(c.detected_type)}</td>
                  <td class="num">${window.UI.formatNumber(c.missing_count)} (${c.missing_pct}%)</td>
                  <td class="mono">${window.UI.escapeHtml(mapping[c.name] || 'unmapped')}</td>
                </tr>`
                )
                .join('')}
            </tbody>
          </table>
        </div>
        ${detail.error_message ? `<div class="notice-banner pink"><p class="notice-body">${window.UI.escapeHtml(detail.error_message)}</p></div>` : ''}
      `;
    } catch (err) {
      body.innerHTML = `<div class="notice-banner pink"><p class="notice-body">${window.UI.escapeHtml(err.message)}</p></div>`;
    }
  }

  async function deleteDataset(id, name) {
    // Use custom in-page confirm modal or direct API action with toast
    const modal = document.getElementById('dataset-detail-modal');
    const title = document.getElementById('modal-dataset-title');
    const sub = document.getElementById('modal-dataset-sub');
    const body = document.getElementById('modal-dataset-body');
    title.textContent = `Delete "${name}"?`;
    sub.textContent = 'This removes the dataset record, imported rows linked exclusively to this dataset, and preserved CSV copy.';
    body.innerHTML = `
      <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 8px;">
        <button type="button" class="btn btn-outline" id="confirm-cancel-btn">Cancel</button>
        <button type="button" class="btn btn-primary" id="confirm-delete-btn">Confirm Delete</button>
      </div>`;
    modal.classList.add('open');

    document.getElementById('confirm-cancel-btn').addEventListener('click', () => modal.classList.remove('open'));
    document.getElementById('confirm-delete-btn').addEventListener('click', async () => {
      try {
        await window.API.del(`/api/datasets/${id}`);
        modal.classList.remove('open');
        window.UI.toast(`Deleted dataset "${name}".`);
        await loadDataManagement();
      } catch (err) {
        window.UI.toast(err.message, 'error');
      }
    });
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const user = await window.UI.initShell('datasets');
    if (!user) return;
    document.getElementById('dm-refresh-btn').addEventListener('click', loadDataManagement);
    document.getElementById('modal-close-btn').addEventListener('click', () => {
      document.getElementById('dataset-detail-modal').classList.remove('open');
    });
    await loadDataManagement();
  });
})();
