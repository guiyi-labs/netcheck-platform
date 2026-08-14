(function () {
  'use strict';
  if (!Auth.requireAuth()) return;
  Auth.renderNav('app-nav');
  var assetId = new URLSearchParams(location.search).get('asset_id');
  var state = { page: 1, pageSize: 20, total: 0 };
  var tbody = document.getElementById('changes-tbody');
  var errorBox = document.getElementById('page-error');
  function escapeHtml(v) { return v == null ? '' : String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function showError(msg) { errorBox.textContent = msg; errorBox.classList.remove('d-none'); } function hideError() { errorBox.classList.add('d-none'); errorBox.textContent = ''; }
  function fmtTime(v) { if (!v) return '-'; var d = new Date(v); return isNaN(d.getTime()) ? escapeHtml(v) : d.toLocaleString('zh-CN', { hour12: false }); }
  function actionBadge(action) { return { create: '<span class="badge text-bg-success">新增</span>', update: '<span class="badge text-bg-primary">更新</span>', delete: '<span class="badge text-bg-danger">删除</span>' }[action] || escapeHtml(action); }
  function fieldLabel(f) { return { name: '名称', ip: 'IP', hostname: '主机名', asset_type: '资产类型', location: '区域', os_type: '操作系统', business_name: '业务系统', ports: '端口', owner: '负责人', status: '状态', remark: '备注' }[f] || escapeHtml(f || '综合'); }
  function renderCell(item) {
    if (item.action === 'create') return '<pre class="diff-block">' + escapeHtml(item.new_value || item.detail || '') + '</pre>';
    if (item.action === 'delete') return '<pre class="diff-block">' + escapeHtml(item.old_value || '') + '</pre>';
    return '<div class="small text-muted mb-1">旧值</div><pre class="diff-block text-danger">' + escapeHtml(item.old_value || '-') + '</pre><div class="small text-muted mt-1 mb-1">新值</div><pre class="diff-block text-success">' + escapeHtml(item.new_value || '-') + '</pre>';
  }
  function pagination() { var pages = Math.max(1, Math.ceil(state.total / state.pageSize)); document.getElementById('page-info').textContent = '共 ' + state.total + ' 条 | 第 ' + state.page + '/' + pages + ' 页'; document.getElementById('btn-prev').disabled = state.page <= 1; document.getElementById('btn-next').disabled = state.total === 0 || state.page >= pages; }
  async function loadChanges() {
    hideError(); tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-4">加载中...</td></tr>';
    try {
      var data = await api.get('/api/assets/' + encodeURIComponent(assetId) + '/changes?page=' + state.page + '&page_size=' + state.pageSize);
      state.total = data.total || 0;
      var items = data.items || [];
      tbody.innerHTML = items.length ? items.map(function (item) { return '<tr><td class="text-nowrap">' + fmtTime(item.changed_at) + '</td><td>' + actionBadge(item.action) + '</td><td>' + fieldLabel(item.field) + '</td><td>' + renderCell(item) + '</td><td>' + escapeHtml(item.username) + '</td></tr>'; }).join('') : '<tr><td colspan="5" class="empty-state"><i class="bi bi-clock-history"></i><div>该资产暂无变更记录</div></td></tr>';
      pagination();
    } catch (err) { tbody.innerHTML = ''; state.total = 0; pagination(); showError('加载变更历史失败：' + err.message); }
  }
  async function loadAsset() {
    try { var a = await api.get('/api/assets/' + encodeURIComponent(assetId)); document.getElementById('asset-caption').textContent = '资产：' + (a.name || a.ip); } catch (err) { document.getElementById('asset-caption').textContent = '资产 #' + assetId; }
  }
  document.getElementById('btn-refresh').addEventListener('click', function () { loadChanges(); });
  document.getElementById('btn-prev').addEventListener('click', function () { if (state.page > 1) { state.page--; loadChanges(); } });
  document.getElementById('btn-next').addEventListener('click', function () { if (state.page < Math.ceil(state.total / state.pageSize)) { state.page++; loadChanges(); } });
  loadAsset(); loadChanges();
})();