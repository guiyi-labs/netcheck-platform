(function () {
  'use strict';
  if (!Auth.requireAuth()) return;
  Auth.renderNav('app-nav');
  var errorBox = document.getElementById('page-error');
  function showError(msg) { errorBox.textContent = msg; errorBox.classList.remove('d-none'); } function hideError() { errorBox.classList.add('d-none'); errorBox.textContent = ''; }
  function escapeHtml(v) { return v == null ? '' : String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  var charts = {};
  function getChart(id) { if (!charts[id]) charts[id] = echarts.init(document.getElementById(id), null, { renderer: 'canvas' }); return charts[id]; }
  function baseOption(title, xData, series) {
    return { title: { text: title, left: 'center', textStyle: { fontSize: 14 } }, tooltip: { trigger: 'axis' }, legend: { top: 28 }, grid: { left: 50, right: 20, top: 60, bottom: 30 }, xAxis: { type: 'category', data: xData }, yAxis: { type: 'value' }, series: series };
  }
  function renderRtt(items) {
    var dates = items.map(function (i) { return i.date; });
    getChart('chart-rtt').setOption(baseOption('响应耗时趋势 (ms)', dates, [
      { name: '平均耗时', type: 'line', smooth: true, data: items.map(function (i) { return i.avg_response_ms; }), itemStyle: { color: '#0d6efd' }, areaStyle: { opacity: 0.15 } },
      { name: '最大耗时', type: 'line', smooth: true, lineStyle: { type: 'dashed' }, data: items.map(function (i) { return i.max_response_ms; }), itemStyle: { color: '#dc3545' } },
    ]), true);
  }
  function renderAvail(items) {
    var dates = items.map(function (i) { return i.date; });
    getChart('chart-avail').setOption(baseOption('可用率 SLA (%)', dates, [
      { name: '可用率', type: 'bar', data: items.map(function (i) { return i.rate; }), itemStyle: { color: function (p) { return p.value >= 99 ? '#198754' : p.value >= 95 ? '#ffc107' : '#dc3545'; } }, label: { show: true, position: 'top', formatter: function (p) { return p.value + '%'; } } },
    ]), true);
  }
  function renderDuration(items) {
    var names = items.map(function (i) { return '#' + i.run_id + ' ' + (i.task_name || '').slice(0, 12); });
    getChart('chart-duration').setOption(baseOption('最近运行耗时 (秒)', names, [
      { name: '运行耗时', type: 'bar', data: items.map(function (i) { return i.duration_s; }), barMaxWidth: 28, itemStyle: { color: '#6610f2' }, label: { show: true, position: 'top', formatter: function (p) { return p.value == null ? '-' : p.value + 's'; } } },
    ]), true);
  }
  var assetId = null;
  async function loadAssets() {
    try {
      var items = await api.get('/api/stats/assets');
      var select = document.getElementById('asset-select');
      select.innerHTML = items.map(function (a) { return '<option value="' + a.id + '">' + escapeHtml(a.name) + (a.ip ? ' (' + escapeHtml(a.ip) + ')' : '') + '</option>'; }).join('');
      if (items.length) assetId = String(items[0].id);
      select.value = assetId;
      return true;
    } catch (err) { showError('加载资产失败：' + err.message); return false; }
  }
  async function loadAll() {
    hideError();
    var days = Number(document.getElementById('days-input').value) || 14;
    assetId = document.getElementById('asset-select').value;
    try {
      var [rtt, avail, durations] = await Promise.all([
        api.get('/api/stats/rtt-trend?asset_id=' + assetId + '&days=' + days),
        api.get('/api/stats/availability?asset_id=' + assetId + '&days=' + days),
        api.get('/api/stats/run-durations?days=' + days),
      ]);
      renderRtt(rtt);
      renderAvail(avail);
      renderDuration(durations);
    } catch (err) { showError('加载趋势数据失败：' + err.message); }
  }
  document.getElementById('btn-refresh').addEventListener('click', loadAll);
  document.getElementById('asset-select').addEventListener('change', loadAll);
  document.getElementById('days-input').addEventListener('change', loadAll);
  window.addEventListener('resize', function () { Object.keys(charts).forEach(function (k) { charts[k].resize(); }); });
  loadAssets().then(function (ok) { if (ok) loadAll(); });
})();