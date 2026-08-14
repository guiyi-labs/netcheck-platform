(function () {
  'use strict';
  if (!Auth.requireAuth()) return;
  Auth.renderNav('app-nav');
  var state = { page: 1, pageSize: 20, total: 0 };
  var tbody = document.getElementById('logs-tbody');
  var errorBox = document.getElementById('page-error');
  function escapeHtml(v) { return v == null ? '' : String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function showError(msg) { errorBox.textContent = msg; errorBox.classList.remove('d-none'); } function hideError() { errorBox.classList.add('d-none'); errorBox.textContent = ''; }
  function fmtTime(value) { if (!value) return '-'; var d = new Date(value); return isNaN(d.getTime()) ? escapeHtml(value) : d.toLocaleString('zh-CN', { hour12: false }); }
  function actionLabel(action) { return { 'auth.login': '登录', 'auth.logout': '退出', 'asset.create': '新增资产', 'asset.update': '更新资产', 'asset.delete': '删除资产', 'task.create': '新建任务', 'task.update': '更新任务', 'task.enable': '启用任务', 'task.disable': '停用任务', 'task.run': '执行任务', 'alert.confirm': '确认告警', 'alert.recover': '恢复告警', 'alert_policy.update': '更新策略', 'report.generate': '生成报告', 'report.delete': '删除报告', 'discovery.scan': '资产发现', 'discovery.import': '导入资产' }[action] || action || '-'; }
  function pagination() { var pages = Math.max(1, Math.ceil(state.total / state.pageSize)); document.getElementById('page-info').textContent = '共 ' + state.total + ' 条 | 第 ' + state.page + '/' + pages + ' 页'; document.getElementById('btn-prev').disabled = state.page <= 1; document.getElementById('btn-next').disabled = state.total === 0 || state.page >= pages; }
  async function loadLogs() {
    hideError(); tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">加载中...</td></tr>';
    try {
      var params = new URLSearchParams({ page: state.page, page_size: state.pageSize });
      var user = document.getElementById('f-user').value.trim(), action = document.getElementById('f-action').value.trim(), target = document.getElementById('f-target').value.trim(), start = document.getElementById('f-start').value, end = document.getElementById('f-end').value;
      if (user) params.set('username', user);
      if (action) params.set('action', action);
      if (target) params.set('target_type', target);
      if (start) params.set('start_date', start);
      if (end) params.set('end_date', end);
      var data = await api.get('/api/audit-logs?' + params.toString());
      state.total = data && data.total || 0;
      var items = data && data.items || [];
      tbody.innerHTML = items.length ? items.map(function (log) { return '<tr><td class="text-nowrap">' + fmtTime(log.created_at) + '</td><td>' + escapeHtml(log.username) + '</td><td><span class="badge text-bg-light border">' + escapeHtml(actionLabel(log.action)) + '</span></td><td>' + escapeHtml(log.target_type || '-') + '</td><td>' + (log.target_id == null ? '-' : escapeHtml(log.target_id)) + '</td><td class="text-truncate-cell" title="' + escapeHtml(log.detail || '') + '">' + escapeHtml(log.detail || '-') + '</td><td>' + escapeHtml(log.ip || '-') + '</td></tr>'; }).join('') : '<tr><td colspan="7" class="empty-state"><i class="bi bi-inbox"></i><div>暂无日志记录</div></td></tr>';
      pagination();
    } catch (err) { tbody.innerHTML = ''; state.total = 0; pagination(); showError('加载审计日志失败：' + err.message); }
  }
  document.getElementById('filter-form').addEventListener('submit', function (e) { e.preventDefault(); state.page = 1; loadLogs(); });
  document.getElementById('btn-refresh').addEventListener('click', function () { loadLogs(); });
  document.getElementById('btn-prev').addEventListener('click', function () { if (state.page > 1) { state.page--; loadLogs(); } });
  document.getElementById('btn-next').addEventListener('click', function () { if (state.page < Math.ceil(state.total / state.pageSize)) { state.page++; loadLogs(); } });
  loadLogs();
})();