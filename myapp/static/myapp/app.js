/* HelpDesk UI behaviour: theme toggle, toasts, clickable rows, shortcuts, dashboard charts. */
(function () {
  'use strict';

  // ---- Theme toggle (initial theme is set inline in <head> to avoid a flash) ----
  function setTheme(theme) {
    document.documentElement.setAttribute('data-bs-theme', theme);
    try { localStorage.setItem('hd-theme', theme); } catch (e) { /* storage unavailable */ }
    document.dispatchEvent(new CustomEvent('hd:theme', { detail: theme }));
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-theme-toggle]');
    if (!btn) return;
    var current = document.documentElement.getAttribute('data-bs-theme');
    setTheme(current === 'dark' ? 'light' : 'dark');
  });

  // ---- Toast messages: auto-dismiss after 6s ----
  document.querySelectorAll('.toast-msg').forEach(function (el, i) {
    var close = function () { el.classList.add('hide'); setTimeout(function () { el.remove(); }, 300); };
    var btn = el.querySelector('.btn-close');
    if (btn) btn.addEventListener('click', close);
    if (!el.classList.contains('sticky')) setTimeout(close, 6000 + i * 600);
  });

  // ---- Clickable table rows ----
  document.addEventListener('click', function (e) {
    var row = e.target.closest('tr[data-href]');
    if (!row || e.target.closest('a, button, input, select, label, form')) return;
    if (e.ctrlKey || e.metaKey) { window.open(row.dataset.href, '_blank'); } else { window.location = row.dataset.href; }
  });

  // ---- "/" focuses the global search ----
  document.addEventListener('keydown', function (e) {
    if (e.key !== '/' || /input|textarea|select/i.test(document.activeElement.tagName)) return;
    var search = document.getElementById('global-search');
    if (search) { e.preventDefault(); search.focus(); }
  });

  // ---- Show the chosen file name for attachment inputs ----
  document.querySelectorAll('input[type=file][data-file-label]').forEach(function (input) {
    var label = document.getElementById(input.dataset.fileLabel);
    input.addEventListener('change', function () {
      if (label) label.textContent = input.files.length ? input.files[0].name : 'Attach file';
    });
  });

  // ---- Demo account quick-fill on the login page ----
  document.querySelectorAll('[data-demo-user]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var u = document.getElementById('id_username'), p = document.getElementById('id_password');
      if (u && p) { u.value = btn.dataset.demoUser; p.value = btn.dataset.demoPass; p.focus(); }
    });
  });

  // ---- Dashboard charts (Chart.js is only loaded on the dashboard) ----
  var STATUS_COLORS = {
    open: '#2e90fa', in_progress: '#7a5af8', on_hold: '#f79009',
    resolved: '#12b76a', closed: '#98a2b3', reopened: '#f04438'
  };
  var charts = [];

  function readJSON(id) {
    var el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  }

  function themeColors() {
    var css = getComputedStyle(document.documentElement);
    return { text: css.getPropertyValue('--hd-muted').trim(), grid: css.getPropertyValue('--hd-border').trim(),
             surface: css.getPropertyValue('--hd-surface').trim(), textStrong: css.getPropertyValue('--hd-text').trim() };
  }

  function drawCharts() {
    if (!window.Chart) return;
    charts.forEach(function (c) { c.destroy(); });
    charts = [];
    var t = themeColors();
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.color = t.text;

    var status = readJSON('status-chart-data');
    var statusEl = document.getElementById('statusChart');
    if (status && statusEl) {
      var total = status.data.reduce(function (a, b) { return a + b; }, 0);
      statusChart = new Chart(statusEl, {
        type: 'doughnut',
        data: { labels: status.labels, datasets: [{
          data: status.data, backgroundColor: status.colors, hoverBackgroundColor: status.colors,
          borderWidth: 4, borderColor: t.surface, hoverBorderColor: t.surface, borderRadius: 4, hoverOffset: 8
        }] },
        options: {
          cutout: '64%', maintainAspectRatio: false, layout: { padding: 10 },
          plugins: {
            legend: { display: false },
            tooltip: {
              padding: 10, cornerRadius: 10, boxPadding: 4, usePointStyle: true,
              backgroundColor: t.surface, titleColor: t.textStrong, bodyColor: t.text, borderColor: t.grid, borderWidth: 1,
              callbacks: { label: function (ctx) {
                return ' ' + ctx.label + ': ' + ctx.parsed + ' (' + Math.round(ctx.parsed / total * 100) + '%)';
              } }
            }
          }
        }
      });
      charts.push(statusChart);
    }

    var trendEl = document.getElementById('trendChart');
    if (trendData && trendEl) {
      trendChart = new Chart(trendEl, {
        type: 'line',
        data: { labels: trendData.labels, datasets: [
          areaDataset('Raised', trendData.created, '59, 130, 246'),
          areaDataset('Resolved', trendData.resolved, '18, 183, 106')
        ] },
        options: {
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          layout: { padding: { top: 6 } },
          plugins: {
            legend: { display: false },
            tooltip: {
              padding: 12, cornerRadius: 12, boxPadding: 5, usePointStyle: true, caretSize: 0,
              backgroundColor: t.surface, titleColor: t.textStrong, bodyColor: t.text, borderColor: t.grid, borderWidth: 1,
              titleFont: { weight: '600' }
            }
          },
          scales: {
            x: { grid: { display: false }, border: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 18 } },
            y: { beginAtZero: true, suggestedMax: 4, ticks: { precision: 0, maxTicksLimit: 5 },
                 grid: { color: t.grid }, border: { display: false, dash: [4, 4] } }
          }
        },
        plugins: [crosshair]
      });
      charts.push(trendChart);
    }
  }

  // Hovering a legend row highlights the matching doughnut segment.
  var statusChart = null;
  document.querySelectorAll('[data-legend-index]').forEach(function (link) {
    var index = parseInt(link.dataset.legendIndex, 10);
    link.addEventListener('mouseenter', function () {
      if (!statusChart || !statusChart.data.datasets[0].data[index]) return;
      var el = [{ datasetIndex: 0, index: index }];
      statusChart.setActiveElements(el);
      statusChart.tooltip.setActiveElements(el, { x: 0, y: 0 });
      statusChart.update();
    });
    link.addEventListener('mouseleave', function () {
      if (!statusChart) return;
      statusChart.setActiveElements([]);
      statusChart.tooltip.setActiveElements([], { x: 0, y: 0 });
      statusChart.update();
    });
  });

  // Smooth line with a soft gradient fill and ringed dots on each point.
  function areaDataset(label, data, rgb) {
    var surface = themeColors().surface;
    var many = data.length > 20;
    return {
      label: label, data: data, fill: true, tension: 0.4, cubicInterpolationMode: 'monotone',
      borderColor: 'rgb(' + rgb + ')', borderWidth: 2.5,
      pointRadius: many ? 3 : 4.5, pointHoverRadius: many ? 6 : 7,
      pointBorderWidth: 2.5, pointHoverBorderWidth: 3,
      pointBackgroundColor: surface, pointBorderColor: 'rgb(' + rgb + ')',
      pointHoverBackgroundColor: 'rgb(' + rgb + ')', pointHoverBorderColor: surface,
      backgroundColor: function (ctx) {
        var area = ctx.chart.chartArea;
        if (!area) return 'rgba(' + rgb + ', .15)';
        var g = ctx.chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
        g.addColorStop(0, 'rgba(' + rgb + ', .28)');
        g.addColorStop(1, 'rgba(' + rgb + ', 0)');
        return g;
      }
    };
  }

  // Vertical guide line at the hovered position.
  var crosshair = {
    id: 'crosshair',
    afterDraw: function (chart) {
      var active = chart.tooltip && chart.tooltip.getActiveElements();
      if (!active || !active.length) return;
      var x = active[0].element.x, area = chart.chartArea, c = chart.ctx;
      c.save();
      c.beginPath(); c.moveTo(x, area.top); c.lineTo(x, area.bottom);
      c.lineWidth = 1; c.strokeStyle = themeColors().grid; c.setLineDash([4, 4]); c.stroke();
      c.restore();
    }
  };

  // ---- Trend range selector (Today / 2 days / 7 days / 30 days / custom) ----
  var trendData = readJSON('trend-chart-data');
  var trendChart = null;
  var trendCard = document.getElementById('trendCard');

  // ▲/▼ badge comparing with the previous period. `upIsGood` decides the colour.
  function renderDelta(el, current, previous, upIsGood) {
    el.className = 'delta';
    if (previous === 0 && current === 0) { el.textContent = '—'; el.classList.add('flat'); return; }
    if (previous === 0) { el.textContent = 'new'; el.classList.add(upIsGood ? 'good' : 'bad'); return; }
    var pct = Math.round((current - previous) / previous * 100);
    if (pct === 0) { el.textContent = '0%'; el.classList.add('flat'); return; }
    el.textContent = (pct > 0 ? '▲ ' : '▼ ') + Math.abs(pct) + '%';
    el.classList.add((pct > 0) === upIsGood ? 'good' : 'bad');
    el.title = 'Previous period: ' + previous;
  }

  function showTrend(data) {
    trendData = data;
    document.getElementById('trendTitle').textContent = data.title;
    document.getElementById('trendPrevLabel').textContent = data.prev_label;
    document.getElementById('trendCreated').textContent = data.total_created;
    document.getElementById('trendResolved').textContent = data.total_resolved;
    renderDelta(document.getElementById('trendCreatedDelta'), data.total_created, data.prev_created, false);
    renderDelta(document.getElementById('trendResolvedDelta'), data.total_resolved, data.prev_resolved, true);
    var net = data.total_created - data.total_resolved;
    var netEl = document.getElementById('trendNet');
    netEl.textContent = (net > 0 ? '+' : '') + net;
    netEl.className = net > 0 ? 'text-danger' : (net < 0 ? 'text-success' : '');
    document.getElementById('trendNetNote').textContent =
      net > 0 ? 'backlog grew' : (net < 0 ? 'backlog shrank' : 'no change');
    document.getElementById('trendEmpty').classList.toggle('d-none', data.total_created + data.total_resolved > 0);
    if (trendChart) drawCharts();  // rebuild so dot sizes suit the new number of points
  }

  function loadTrend(params) {
    var error = document.getElementById('trendError');
    var loading = document.getElementById('trendLoading');
    error.textContent = '';
    loading.classList.remove('d-none');
    fetch(trendCard.dataset.url + '?' + new URLSearchParams(params), { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (!res.ok) { error.textContent = res.body.error || 'Could not load data.'; return; }
        showTrend(res.body);
      })
      .catch(function () { error.textContent = 'Could not load data. Check your connection.'; })
      .finally(function () { loading.classList.add('d-none'); });
  }

  if (trendCard) {
    var rangeSelect = document.getElementById('trendRange');
    var customForm = document.getElementById('trendCustom');
    var fromInput = document.getElementById('trendFrom');
    var toInput = document.getElementById('trendTo');
    var saved = null;
    try { saved = localStorage.getItem('hd-trend-range'); } catch (e) {}

    rangeSelect.addEventListener('change', function () {
      var value = rangeSelect.value;
      customForm.classList.toggle('d-none', value !== 'custom');
      if (value === 'custom') {
        if (!toInput.value) toInput.value = toInput.max;
        if (!fromInput.value) {
          var d = new Date(toInput.value); d.setDate(d.getDate() - 13);
          fromInput.value = d.toISOString().slice(0, 10);
        }
        fromInput.focus();
        return;
      }
      try { localStorage.setItem('hd-trend-range', value); } catch (e) {}
      loadTrend({ range: value });
    });

    customForm.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!fromInput.value || !toInput.value) {
        document.getElementById('trendError').textContent = 'Choose both dates.';
        return;
      }
      loadTrend({ range: 'custom', from: fromInput.value, to: toInput.value });
    });

    // Restore the last range the user picked (custom ranges are not remembered).
    if (saved && saved !== rangeSelect.value && rangeSelect.querySelector('option[value="' + saved + '"]')) {
      rangeSelect.value = saved;
      loadTrend({ range: saved });
    }
  }

  if (trendData && document.getElementById('trendCreatedDelta')) showTrend(trendData);
  drawCharts();
  document.addEventListener('hd:theme', function () { setTimeout(drawCharts, 50); });
})();
