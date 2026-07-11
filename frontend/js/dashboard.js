(function () {
  'use strict';
  if (!Auth.requireAuth()) return;
  Auth.renderNav('app-nav');

  var charts = {};
  var errorBox = document.getElementById('dashboard-error');
  var tbody = document.getElementById('recent-abnormal-tbody');
  var numberIds = ['asset_total', 'online_assets', 'offline_assets', 'warning_assets', 'unknown_assets', 'task_total', 'run_total', 'today_runs', 'today_abnormal_results', 'diagnosis_total', 'active_alerts', 'unconfirmed_alerts', 'recovered_alerts_today'];

  function escapeHtml(value) {
    return value == null ? '' : String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function fmtTime(value) {
    if (!value) return '-';
    var date = new Date(value);
    return isNaN(date.getTime()) ? escapeHtml(value) : date.toLocaleString('zh-CN', { hour12: false });
  }
  function label(type) {
    return { ping: 'Ping', port: '端口', http: 'HTTP' }[type] || type || '-';
  }
  function showError(message) { errorBox.textContent = message; errorBox.classList.remove('d-none'); }
  function hideError() { errorBox.textContent = ''; errorBox.classList.add('d-none'); }
  function setText(id, value) { var el = document.getElementById(id); if (el) el.textContent = value == null ? '--' : value; }
  function getItems(data) { return Array.isArray(data) ? data : ((data && data.items) || []); }
  function renderChart(id, option, emptyMessage) {
    var el = document.getElementById(id), fallbackEl = document.getElementById(id.replace('-chart', '-fallback'));
    if (fallbackEl) fallbackEl.classList.add('d-none');
    if (!window.echarts) { if (el) el.classList.add('d-none'); if (fallbackEl) { fallbackEl.textContent = '图表库加载失败，请刷新页面后重试。'; fallbackEl.classList.remove('d-none'); } return; }
    if (!option.series || !option.series.length || option.series.every(function (s) { return !s.data || !s.data.length; })) { if (el) el.classList.add('d-none'); if (fallbackEl) { fallbackEl.textContent = emptyMessage || '暂无数据'; fallbackEl.classList.remove('d-none'); } return; }
    el.classList.remove('d-none');
    if (charts[id]) charts[id].dispose();
    charts[id] = echarts.init(el);
    charts[id].setOption(option);
  }
  function commonTooltip() { return { trigger: 'axis' }; }
  function renderAssetStatus(items) {
    var data = (items || []).map(function (item) { return { name: item.name || '未知', value: Number(item.count) || 0 }; });
    renderChart('asset-status-chart', { tooltip: { trigger: 'item' }, legend: { bottom: 0 }, series: [{ type: 'pie', radius: ['42%', '70%'], data: data, label: { formatter: '{b}: {c}' } }] }, '暂无资产状态数据');
  }
  function renderTrend(items) {
    var rows = items || [];
    renderChart('trend-chart', { tooltip: commonTooltip(), legend: { bottom: 0 }, grid: { left: 40, right: 20, top: 20, bottom: 38 }, xAxis: { type: 'category', data: rows.map(function (x) { return x.date; }) }, yAxis: { type: 'value', minInterval: 1 }, series: [{ name: '巡检次数', type: 'line', smooth: true, data: rows.map(function (x) { return Number(x.runs) || 0; }) }, { name: '异常结果', type: 'line', smooth: true, data: rows.map(function (x) { return Number(x.abnormal_results) || 0; }) }] }, '暂无趋势数据');
  }
  function renderFaultTypes(items) {
    var data = (items || []).map(function (item) { return { name: item.name || '未知', value: Number(item.count) || 0 }; });
    renderChart('fault-types-chart', { tooltip: { trigger: 'item' }, series: [{ type: 'pie', radius: '68%', data: data, label: { formatter: '{b}: {c}' } }] }, '暂无故障类型数据');
  }
  function renderAbnormal(items) {
    if (!items || !items.length) { tbody.innerHTML = '<tr><td colspan="8" class="empty-state"><i class="bi bi-inbox"></i><div>暂无异常记录</div></td></tr>'; return; }
    tbody.innerHTML = items.map(function (item) {
      var text = item.error_message || item.message || '-';
      return '<tr><td class="text-nowrap">' + fmtTime(item.checked_at) + '</td><td>' + escapeHtml(item.task_name || ('任务 #' + item.task_id)) + '</td><td>' + escapeHtml(item.asset_name || ('资产 #' + item.asset_id)) + '</td><td>' + escapeHtml(label(item.check_type)) + '</td><td class="text-truncate-cell" title="' + escapeHtml(item.target || '') + '">' + escapeHtml(item.target || '-') + '</td><td><span class="status-badge ' + (item.status === 'warning' ? 'status-warning' : 'status-failed') + '">' + escapeHtml(item.status || '异常') + '</span></td><td class="text-truncate-cell" title="' + escapeHtml(text) + '">' + escapeHtml(text) + '</td><td class="text-end"><a class="btn btn-sm btn-outline-primary" href="results.html?run_id=' + encodeURIComponent(item.run_id || '') + '">查看</a></td></tr>';
    }).join('');
  }
  async function load() {
    hideError();
    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">加载中...</td></tr>';
    try {
      var data = await Promise.all([
        api.get('/api/dashboard/summary'), api.get('/api/dashboard/asset-status'), api.get('/api/dashboard/trend?days=7'), api.get('/api/dashboard/fault-types?days=7'), api.get('/api/dashboard/recent-abnormal?limit=10')
      ]);
      var summary = data[0] || {};
      numberIds.forEach(function (id) { setText('stat-' + id.replace(/_/g, '-'), summary[id]); });
      renderAssetStatus(getItems(data[1]));
      renderTrend(getItems(data[2]));
      renderFaultTypes(getItems(data[3]));
      renderAbnormal(getItems(data[4]));
      document.getElementById('dashboard-updated').textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
    } catch (err) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty-state"><i class="bi bi-exclamation-circle"></i><div>数据加载失败</div></td></tr>';
      showError('仪表盘加载失败：' + (err.message || err));
    }
  }
  document.getElementById('btn-dashboard-refresh').addEventListener('click', load);
  window.addEventListener('resize', function () { Object.keys(charts).forEach(function (key) { charts[key].resize(); }); });
  load();
})();
