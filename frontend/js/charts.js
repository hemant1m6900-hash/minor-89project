/**
 * Chart.js 4.x helpers strictly constrained to Navy (#0F1B3D), White (#FFFFFF), and Hot Pink (#FF3D8B).
 */
(function (global) {
  const NAVY = '#0F1B3D';
  const PINK = '#FF3D8B';
  const WHITE = '#FFFFFF';
  const NAVY_70 = 'rgba(15, 27, 61, 0.70)';
  const NAVY_40 = 'rgba(15, 27, 61, 0.40)';
  const NAVY_18 = 'rgba(15, 27, 61, 0.18)';
  const NAVY_08 = 'rgba(15, 27, 61, 0.08)';
  const PINK_16 = 'rgba(255, 61, 139, 0.16)';

  const instances = {};

  function destroyChart(id) {
    if (instances[id]) {
      instances[id].destroy();
      delete instances[id];
    }
  }

  function ensureChartLib() {
    return typeof global.Chart !== 'undefined';
  }

  function baseOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            color: NAVY,
            font: { family: "'Plus Jakarta Sans', sans-serif", size: 12, weight: '600' },
            usePointStyle: true,
            boxWidth: 8,
          },
        },
        tooltip: {
          backgroundColor: NAVY,
          titleColor: WHITE,
          bodyColor: WHITE,
          padding: 10,
          cornerRadius: 6,
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: NAVY_70, font: { size: 11 } },
        },
        y: {
          grid: { color: NAVY_08 },
          ticks: { color: NAVY_70, font: { size: 11 } },
        },
      },
    };
  }

  function renderLineOrBar(canvasId, config) {
    if (!ensureChartLib()) return null;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    destroyChart(canvasId);
    const mergedOptions = Object.assign({}, baseOptions(), config.options || {});
    instances[canvasId] = new global.Chart(canvas.getContext('2d'), {
      type: config.type || 'line',
      data: config.data,
      options: mergedOptions,
    });
    return instances[canvasId];
  }

  function renderDoughnut(canvasId, labels, values) {
    if (!ensureChartLib()) return null;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    destroyChart(canvasId);

    const palette = [PINK, NAVY, NAVY_70, NAVY_40, NAVY_18, 'rgba(255, 61, 139, 0.55)'];
    const bgColors = labels.map((_, idx) => palette[idx % palette.length]);

    instances[canvasId] = new global.Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels,
        datasets: [
          {
            data: values,
            backgroundColor: bgColors,
            borderColor: WHITE,
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '64%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: NAVY,
              font: { family: "'Plus Jakarta Sans', sans-serif", size: 12 },
              boxWidth: 10,
              padding: 12,
            },
          },
          tooltip: {
            backgroundColor: NAVY,
            titleColor: WHITE,
            bodyColor: WHITE,
            padding: 10,
            cornerRadius: 6,
          },
        },
      },
    });
    return instances[canvasId];
  }

  global.Charts = {
    COLORS: { NAVY, PINK, WHITE, NAVY_70, NAVY_40, NAVY_18, NAVY_08, PINK_16 },
    destroyChart,
    renderLineOrBar,
    renderDoughnut,
  };
})(window);
