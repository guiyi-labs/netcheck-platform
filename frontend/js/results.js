(function () {
  'use strict';
  if (!Auth.requireAuth()) return;
  Auth.renderNav('app-nav');

  var query = new URLSearchParams(location.search);
  var state = { page: 1, pageSize: 20, total: 0, items: [] };
  var tbody = document.getElementById('results-tbody');
  var error = document.getElementById('page-error');
  var detailModal = new bootstrap.Modal(document.getElementById('detailModal'));
  var fields = { run_id: 'f-run-id', task_id: 'f-task-id', asset_id: 'f-asset-id', check_type: 'f-type', status: 'f-status', start_date: 'f-start-date', end_date: 'f-end-date' };

  function escapeHtml(v) { return v == null ? '' : String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function showError(msg) { error.textContent = msg; error.classList.remove('d-none'); }
  function hideError() { error.textContent = ''; error.classList.add('d-none'); }
  function time(value) { if (!value) return '-'; var d = new Date(value); return isNaN(d.getTime()) ? escapeHtml(value) : d.toLocaleString('zh-CN', { hour12: false }); }
  function statusClass(status) { return { success: 'status-success', warning: 'status-warning', failed: 'status-failed' }[status] || 'status-unknown'; }
  function statusLabel(status) { return { success: '成功', warning: '警告', failed: '失败' }[status] || status || '-'; }
  function typeLabel(type) { return { ping: 'Ping', port: '端口', http: 'HTTP' }[type] || type || '-'; }
  function value(id) { return document.getElementById(id).value.trim(); }
  function setInitialFilters() {
    Object.keys(fields).forEach(function (key) { var v = query.get(key); if (v) document.getElementById(fields[key]).value = v; });
    if (value('f-run-id')) {
      document.getElementById('run-caption').textContent = '运行 ID：' + value('f-run-id');
      var link = document.getElementById('open-diagnosis');
      link.href = 'diagnosis.html?run_id=' + encodeURIComponent(value('f-run-id'));
      link.classList.remove('d-none');
    }
  }
  function buildUrl() {
    var params = new URLSearchParams({ page: String(state.page), page_size: String(state.pageSize) });
    Object.keys(fields).forEach(function (key) { var v = value(fields[key]); if (v) params.set(key, v); });
    return '/api/results?' + params.toString();
  }
  async function loadResults() {
    hideError();
    tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted py-4">加载中...</td></tr>';
    try {
      var data = await api.get(buildUrl());
      state.total = data && data.total || 0;
      state.items = data && data.items || [];
      render();
    } catch (err) {
      state.items = []; state.total = 0; tbody.innerHTML = '';
      showError('加载巡检结果失败：' + (err.message || err));
      renderPager();
    }
  }
  function render() {
    if (!state.items.length) tbody.innerHTML = '<tr><td colspan="10" class="empty-state"><i class="bi bi-inbox"></i><div>暂无符合条件的结果</div></td></tr>';
    else tbody.innerHTML = state.items.map(function (item, index) {
      var text = item.error_message || item.message || '-';
      return '<tr><td>' + escapeHtml(item.id) + '</td><td><div>运行 #' + escapeHtml(item.run_id) + '</div><div class="text-muted small">任务 #' + escapeHtml(item.task_id) + ' ' + escapeHtml(item.task_name || '') + '</div></td><td><div>' + escapeHtml(item.asset_name || ('资产 #' + item.asset_id)) + '</div><div class="text-muted small">ID: ' + escapeHtml(item.asset_id) + '</div></td><td>' + escapeHtml(typeLabel(item.check_type)) + '</td><td class="text-truncate-cell" title="' + escapeHtml(item.target || '') + '">' + escapeHtml(item.target || '-') + '</td><td><span class="status-badge ' + statusClass(item.status) + '">' + escapeHtml(statusLabel(item.status)) + '</span></td><td>' + (item.response_time == null ? '-' : escapeHtml(item.response_time) + ' ms') + '</td><td class="text-truncate-cell" title="' + escapeHtml(text) + '">' + escapeHtml(text) + '</td><td class="text-nowrap">' + time(item.checked_at) + '</td><td class="text-end"><button class="btn btn-sm btn-outline-primary js-detail" data-index="' + index + '">详情</button></td></tr>';
    }).join('');
    renderPager();
  }
  function renderPager() {
    var pages = Math.max(1, Math.ceil(state.total / state.pageSize));
    document.getElementById('page-info').textContent = '共 ' + state.total + ' 条 | 第 ' + state.page + '/' + pages + ' 页';
    document.getElementById('btn-prev').disabled = state.page <= 1;
    document.getElementById('btn-next').disabled = state.total === 0 || state.page >= pages;
  }
  function showDetail(item) {
    var rows = [['结果 ID', item.id], ['运行 ID', item.run_id], ['任务 ID', item.task_id], ['任务名称', item.task_name], ['资产 ID', item.asset_id], ['资产名称', item.asset_name], ['检测类型', typeLabel(item.check_type)], ['目标', item.target], ['状态', statusLabel(item.status)], ['响应耗时', item.response_time == null ? null : item.response_time + ' ms'], ['消息', item.message], ['错误信息', item.error_message], ['检测时间', time(item.checked_at)]];
    document.getElementById('detail-content').innerHTML = rows.map(function (row) { return '<dt class="col-sm-3">' + escapeHtml(row[0]) + '</dt><dd class="col-sm-9 text-break">' + escapeHtml(row[1] == null || row[1] === '' ? '-' : row[1]) + '</dd>'; }).join('');
    detailModal.show();
  }
  setInitialFilters();
  document.getElementById('filter-form').addEventListener('submit', function (event) { event.preventDefault(); state.page = 1; loadResults(); });
  document.getElementById('btn-reset').addEventListener('click', function () { Object.keys(fields).forEach(function (key) { document.getElementById(fields[key]).value = ''; }); state.page = 1; document.getElementById('run-caption').textContent = '全局结果查询'; document.getElementById('open-diagnosis').classList.add('d-none'); loadResults(); });
  document.getElementById('btn-prev').addEventListener('click', function () { if (state.page > 1) { state.page--; loadResults(); } });
  document.getElementById('btn-next').addEventListener('click', function () { if (state.page < Math.ceil(state.total / state.pageSize)) { state.page++; loadResults(); } });
  document.getElementById('btn-refresh').addEventListener('click', loadResults);
  tbody.addEventListener('click', function (event) { var button = event.target.closest('.js-detail'); if (button) showDetail(state.items[Number(button.getAttribute('data-index'))]); });
  loadResults();
})();
