(function () {
  const CANONICAL_FIELDS = [
    { value: '', label: '— Ignore Column —' },
    { value: 'order_id', label: 'Order ID (order_id)' },
    { value: 'order_date', label: 'Order / Sale Date (order_date)' },
    { value: 'transaction_id', label: 'Transaction ID (transaction_id)' },
    { value: 'customer_id', label: 'Customer ID (customer_id)' },
    { value: 'customer_name', label: 'Customer Name (customer_name)' },
    { value: 'customer_email', label: 'Customer Email (customer_email)' },
    { value: 'country', label: 'Country / Region (country)' },
    { value: 'product_id', label: 'Product ID / SKU (product_id)' },
    { value: 'sku', label: 'SKU Code (sku)' },
    { value: 'product_name', label: 'Product Name (product_name)' },
    { value: 'category', label: 'Category (category)' },
    { value: 'quantity', label: 'Quantity (quantity)' },
    { value: 'unit_price', label: 'Unit Price (unit_price)' },
    { value: 'cost_price', label: 'Cost Price (cost_price)' },
    { value: 'total_amount', label: 'Total Amount / Revenue (total_amount)' },
    { value: 'discount_amount', label: 'Discount Amount (discount_amount)' },
    { value: 'stock_quantity', label: 'Stock Quantity (stock_quantity)' },
    { value: 'reorder_level', label: 'Reorder Level (reorder_level)' },
    { value: 'payment_method', label: 'Payment Method (payment_method)' },
    { value: 'status', label: 'Order Status (status)' },
  ];

  let selectedFile = null;
  let activeDatasetId = null;

  function setStep(step) {
    [1, 2, 3, 4].forEach((n) => {
      const ind = document.getElementById(`step-ind-${n}`);
      if (!ind) return;
      ind.classList.remove('active', 'done');
      if (n < step) ind.classList.add('done');
      if (n === step) ind.classList.add('active');
    });
    document.getElementById('upload-step-1').style.display = step === 1 ? 'flex' : 'none';
    document.getElementById('upload-step-2').style.display = step === 2 || step === 3 ? 'flex' : 'none';
    document.getElementById('upload-step-4').style.display = step === 4 ? 'flex' : 'none';
  }

  function showAlert(msg) {
    const slot = document.getElementById('upload-alert-slot');
    slot.innerHTML = `
      <div class="notice-banner pink">
        <div>
          <p class="notice-title">Validation / Upload Notice</p>
          <p class="notice-body">${window.UI.escapeHtml(msg)}</p>
        </div>
      </div>`;
  }

  function clearAlert() {
    document.getElementById('upload-alert-slot').innerHTML = '';
  }

  function renderProfile(profile) {
    activeDatasetId = profile.dataset_id;
    setStep(3);

    const kpis = document.getElementById('profile-summary-kpis');
    kpis.innerHTML = `
      <div class="kpi-card">
        <span class="kpi-label">Total Rows</span>
        <span class="kpi-value">${window.UI.formatNumber(profile.row_count)}</span>
        <span class="kpi-sub">${window.UI.formatNumber(profile.column_count)} columns detected</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Missing Cells</span>
        <span class="kpi-value">${window.UI.formatNumber(profile.missing_cells)}</span>
        <span class="kpi-sub">Across all columns</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Duplicate Rows</span>
        <span class="kpi-value">${window.UI.formatNumber(profile.duplicate_rows)}</span>
        <span class="kpi-sub">Exact row matches</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Auto-Classification</span>
        <span class="kpi-value" style="font-size: 20px; text-transform: capitalize;">${window.UI.escapeHtml(profile.detected_type)}</span>
        <span class="kpi-sub accent">Confidence ${Math.round((profile.classification_confidence || 0) * 100)}%</span>
      </div>
    `;

    document.getElementById('classification-subtitle').textContent =
      `File: ${profile.filename} · ${profile.classification_reason || 'Auto-detected from column semantics'}`;
    document.getElementById('dataset-type-select').value = profile.dataset_type || profile.detected_type || 'orders';

    const suggestedMapping = profile.suggested_mapping || {};
    const tbody = document.getElementById('column-mapping-tbody');
    tbody.innerHTML = (profile.columns || [])
      .map((col) => {
        const mapped = suggestedMapping[col.name] || '';
        const optionsHtml = CANONICAL_FIELDS.map(
          (f) => `<option value="${f.value}" ${f.value === mapped ? 'selected' : ''}>${window.UI.escapeHtml(f.label)}</option>`
        ).join('');
        const samples = (col.sample_values || []).slice(0, 3).map(window.UI.escapeHtml).join(', ');
        return `
          <tr>
            <td><strong>${window.UI.escapeHtml(col.name)}</strong></td>
            <td><span class="status-label">${window.UI.escapeHtml(col.detected_type)}</span></td>
            <td class="num">${window.UI.formatNumber(col.missing_count)} (${col.missing_pct}%)</td>
            <td class="num">${window.UI.formatNumber(col.unique_count)}</td>
            <td style="max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${samples || '—'}</td>
            <td>
              <select class="form-control mapping-select" data-column="${window.UI.escapeHtml(col.name)}">
                ${optionsHtml}
              </select>
            </td>
          </tr>`;
      })
      .join('');

    // Render Raw Preview Table
    const previewTable = document.getElementById('raw-preview-table');
    const cols = (profile.columns || []).map((c) => c.name);
    const rows = profile.preview_rows || [];
    previewTable.innerHTML = `
      <thead><tr>${cols.map((c) => `<th>${window.UI.escapeHtml(c)}</th>`).join('')}</tr></thead>
      <tbody>
        ${rows
          .map(
            (r) =>
              `<tr>${cols
                .map((c) => `<td>${window.UI.escapeHtml(r[c] === null || r[c] === undefined ? '' : r[c])}</td>`)
                .join('')}</tr>`
          )
          .join('')}
      </tbody>`;
  }

  async function loadExistingDatasetForReimport(datasetId) {
    try {
      clearAlert();
      const profile = await window.API.get(`/api/datasets/${datasetId}/preview`);
      renderProfile(profile);
    } catch (err) {
      showAlert(err.message);
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const user = await window.UI.initShell('upload');
    if (!user) return;

    const dropzone = document.getElementById('csv-dropzone');
    const fileInput = document.getElementById('csv-file-input');
    const fileLabel = document.getElementById('selected-file-label');
    const uploadBtn = document.getElementById('btn-upload-analyze');
    const importBtn = document.getElementById('btn-run-import');

    const params = new URLSearchParams(window.location.search);
    const reimportId = params.get('reimport');
    if (reimportId) {
      await loadExistingDatasetForReimport(reimportId);
    }

    function setFile(file) {
      if (!file) return;
      if (!file.name.toLowerCase().endsWith('.csv')) {
        showAlert('Please select a valid .csv file.');
        return;
      }
      clearAlert();
      selectedFile = file;
      fileLabel.textContent = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
      uploadBtn.disabled = false;
    }

    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') fileInput.click();
    });
    fileInput.addEventListener('change', (e) => setFile(e.target.files[0]));
    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
    });

    uploadBtn.addEventListener('click', async () => {
      if (!selectedFile) return;
      clearAlert();
      uploadBtn.disabled = true;
      uploadBtn.textContent = 'Analyzing CSV...';
      try {
        const formData = new FormData();
        formData.append('file', selectedFile);
        const label = document.getElementById('dataset-name-input').value.trim();
        if (label) formData.append('name', label);
        const profile = await window.API.upload('/api/datasets/upload', formData);
        renderProfile(profile);
        window.UI.toast('CSV uploaded and profiled successfully.');
      } catch (err) {
        showAlert(err.message);
      } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Upload & Inspect Schema';
      }
    });

    importBtn.addEventListener('click', async () => {
      if (!activeDatasetId) return;
      clearAlert();
      const mapping = {};
      document.querySelectorAll('.mapping-select').forEach((sel) => {
        if (sel.value) {
          mapping[sel.dataset.column] = sel.value;
        }
      });

      const payload = {
        dataset_type: document.getElementById('dataset-type-select').value,
        column_mapping: mapping,
        cleaning_options: {
          drop_duplicates: document.getElementById('clean-drop-duplicates').checked,
          trim_whitespace: document.getElementById('clean-trim-whitespace').checked,
          missing_numeric: document.getElementById('clean-missing-numeric').value,
          missing_text: document.getElementById('clean-missing-text').value,
        },
      };

      importBtn.disabled = true;
      importBtn.textContent = 'Validating & Importing...';
      try {
        const res = await window.API.post(`/api/datasets/${activeDatasetId}/import`, payload);
        setStep(4);
        document.getElementById('import-result-subtitle').textContent =
          `${res.dataset_name} (${res.dataset_type}) committed to SQLite.`;
        document.getElementById('import-result-status').textContent = (res.status || 'IMPORTED').toUpperCase();
        document.getElementById('import-result-kpis').innerHTML = `
          <div class="kpi-card"><span class="kpi-label">Rows Parsed</span><span class="kpi-value">${window.UI.formatNumber(res.rows_parsed)}</span></div>
          <div class="kpi-card"><span class="kpi-label">Rows Imported</span><span class="kpi-value">${window.UI.formatNumber(res.rows_imported)}</span></div>
          <div class="kpi-card"><span class="kpi-label">Rows Skipped / Cleaned</span><span class="kpi-value">${window.UI.formatNumber(res.rows_skipped)}</span></div>
          <div class="kpi-card"><span class="kpi-label">Duplicates Removed</span><span class="kpi-value">${window.UI.formatNumber(res.duplicates_removed)}</span></div>
        `;
        const warnBox = document.getElementById('import-warnings-box');
        if (res.warnings && res.warnings.length > 0) {
          warnBox.innerHTML = `
            <div class="notice-banner">
              <div>
                <p class="notice-title">Preprocessing Notes</p>
                <p class="notice-body">${res.warnings.map(window.UI.escapeHtml).join(' · ')}</p>
              </div>
            </div>`;
        } else {
          warnBox.innerHTML = '';
        }
        window.UI.toast('Dataset imported into SQLite.');
      } catch (err) {
        showAlert(err.message);
      } finally {
        importBtn.disabled = false;
        importBtn.textContent = 'Validate & Import to SQLite';
      }
    });

    function resetFlow() {
      selectedFile = null;
      activeDatasetId = null;
      fileInput.value = '';
      fileLabel.textContent = 'Accepted format: UTF-8 / Latin-1 CSV files up to 50 MB';
      uploadBtn.disabled = true;
      clearAlert();
      setStep(1);
    }

    document.getElementById('btn-reset-upload').addEventListener('click', resetFlow);
    document.getElementById('btn-upload-another').addEventListener('click', resetFlow);
  });
})();
