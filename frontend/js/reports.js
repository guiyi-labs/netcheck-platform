(function () {
  'use strict';
  if (!Auth.requireAuth()) return;
  Auth.renderNav('app-nav');

  var TOKEN_KEY = 'netcheck_token';
  var state = { page: 1, pageSize: 20, total: 0, items: [] };
  var tbody = document.getElementById('reports-tbody');
  var error = document.getElementById('page-error');
  var success = document.getElementById('page-success');

  function escapeHtml(v) { return v == null ? '' : String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function showError(msg) { error.textContent = msg; error.classList.remove('d-none'); }
  function hideError() { error.textContent = ''; error.classList.add('d-none'); }
  function showSuccess(msg) { success.textContent = msg; success.classList.remove('d-none'); }
  function hideSuccess() { success.textContent = ''; success.classList.add('d-none'); }
  function fmtTime(value) { if (!value) return '-'; var d = new Date(value); return isNaN(d.getTime()) ? escapeHtml(value) : d.toLocaleString('zh-CN', { hour12: false }); }
  function typeLabel(type) { return { run: '运行报告', daily: '日报' }[type] || type || '-'; }
  function fileSize(size) { var n = Number(size) || 0; if (n >= 1048576) return (n / 1048576).toFixed(2) + ' MB'; if (n >= 1024) return (n / 1024).toFixed(1) + ' KB'; return n + ' B'; }
  function today() { var d = new Date(); var p = function (n) { return n < 10 ? '0' + n : '' + n; }; return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()); }
  function buildListUrl() {
    var params = new URLSearchParams({ page: String(state.page), page_size: String(state.pageSize) });
    var reportType = document.getElementById('f-report-type').value;
    if (reportType) params.set('report_type', reportType);
    return '/api/reports?' + params.toString();
  }
  async function loadReports() {
    hideError(); hideSuccess();
    tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-4">加载中...</td></tr>';
    try {
      var data = await api.get(buildListUrl());
      state.total = data && data.total || 0;
      state.items = data && data.items || [];
      render();
    } catch (err) {
      state.items = []; state.total = 0; tbody.innerHTML = '';
      showError('加载报告列表失败：' + (err.message || err));
      renderPager();
    }
  }
  function render() {
    if (!state.items.length) tbody.innerHTML = '<tr><td colspan="9" class="empty-state"><i class="bi bi-inbox"></i><div>暂无报告</div></td></tr>';
    else tbody.innerHTML = state.items.map(function (item, index) {
      return '<tr><td>' + escapeHtml(item.id) + '</td><td>' + escapeHtml(item.report_name) + '</td><td><span class="status-badge status-running">' + escapeHtml(typeLabel(item.report_type)) + '</span></td><td>' + escapeHtml(item.report_date || '-') + '</td><td><div>运行：' + escapeHtml(item.run_id || '-') + '</div><div class="text-muted small">任务：' + escapeHtml(item.task_id || '-') + '</div></td><td class="text-truncate-cell" title="' + escapeHtml(item.file_name || '') + '">' + escapeHtml(item.file_name || '-') + '</td><td>' + escapeHtml(fileSize(item.file_size)) + '</td><td class="text-nowrap">' + fmtTime(item.created_at) + '</td><td class="text-end"><button class="btn btn-sm btn-outline-primary me-1 js-download" data-index="' + index + '"><i class="bi bi-download"></i></button><button class="btn btn-sm btn-outline-danger js-delete" data-index="' + index + '"><i class="bi bi-trash"></i></button></td></tr>';
    }).join('');
    renderPager();
  }
  function renderPager() {
    var pages = Math.max(1, Math.ceil(state.total / state.pageSize));
    document.getElementById('page-info').textContent = '共 ' + state.total + ' 条 | 第 ' + state.page + '/' + pages + ' 页';
    document.getElementById('btn-prev').disabled = state.page <= 1;
    document.getElementById('btn-next').disabled = state.total === 0 || state.page >= pages;
  }
  async function generate(payload) {
    hideError(); hideSuccess();
    try {
      await api.post('/api/reports/generate', payload);
      state.page = 1;
      await loadReports();
      showSuccess('报告已生成');
    } catch (err) { showError('生成报告失败：' + (err.message || err)); }
  }
  async function downloadReport(item) {
    hideError(); hideSuccess();
    try {
      var token = localStorage.getItem(TOKEN_KEY) || '';
      var resp = await fetch('/api/reports/' + encodeURIComponent(item.id) + '/download', { headers: token ? { Authorization: 'Bearer ' + token } : {} });
      if (resp.status === 401 && token) { localStorage.removeItem(TOKEN_KEY); location.href = 'login.html'; return; }
      if (!resp.ok) throw new Error('下载失败 HTTP ' + resp.status);
      var blob = await resp.blob();
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = item.file_name || ('report-' + item.id + '.xlsx');
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) { showError('下载报告失败：' + (err.message || err)); }
  }
  async function deleteReport(item) {
    if (!confirm('确认删除报告：' + item.report_name + '？')) return;
    hideError(); hideSuccess();
    try {
      await api.del('/api/reports/' + encodeURIComponent(item.id));
      if (state.items.length === 1 && state.page > 1) state.page--;
      await loadReports();
      showSuccess('报告已删除');
    } catch (err) { showError('删除报告失败：' + (err.message || err)); }
  }

  document.getElementById('report-date').value = today();
  new URLSearchParams(location.search).forEach(function (value, key) { if (key === 'run_id') document.getElementById('run-id').value = value; });
  document.getElementById('run-report-form').addEventListener('submit', function (event) { event.preventDefault(); var runId = document.getElementById('run-id').value.trim(); if (!runId) return; generate({ report_type: 'run', run_id: Number(runId) }); });
  document.getElementById('daily-report-form').addEventListener('submit', function (event) { event.preventDefault(); var date = document.getElementById('report-date').value; if (!date) return; generate({ report_type: 'daily', report_date: date }); });
  document.getElementById('filter-form').addEventListener('submit', function (event) { event.preventDefault(); state.page = 1; loadReports(); });
  document.getElementById('btn-reset').addEventListener('click', function () { document.getElementById('f-report-type').value = ''; state.page = 1; loadReports(); });
  document.getElementById('btn-refresh').addEventListener('click', loadReports);
  document.getElementById('btn-prev').addEventListener('click', function () { if (state.page > 1) { state.page--; loadReports(); } });
  document.getElementById('btn-next').addEventListener('click', function () { if (state.page < Math.ceil(state.total / state.pageSize)) { state.page++; loadReports(); } });
  tbody.addEventListener('click', function (event) { var download = event.target.closest('.js-download'), del = event.target.closest('.js-delete'); if (download) downloadReport(state.items[Number(download.getAttribute('data-index'))]); if (del) deleteReport(state.items[Number(del.getAttribute('data-index'))]); });
  loadReports();
})();
