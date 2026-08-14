(function () {
  'use strict';
  if (!Auth.requireAuth()) return;
  Auth.renderNav('app-nav');
  var me = Auth.currentUser() || {};
  if (me.role !== 'admin') {
    document.getElementById('page-error').textContent = '该页面仅管理员可访问。';
    document.getElementById('page-error').classList.remove('d-none');
    return;
  }
  var state = { page: 1, pageSize: 20, total: 0, items: [], editingId: null };
  var tbody = document.getElementById('users-tbody');
  var errorBox = document.getElementById('page-error');
  var modal = new bootstrap.Modal(document.getElementById('userModal'));
  function escapeHtml(v) { return v == null ? '' : String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function showError(msg) { errorBox.textContent = msg; errorBox.classList.remove('d-none'); } function hideError() { errorBox.classList.add('d-none'); errorBox.textContent = ''; }
  function roleLabel(r) { return { admin: '管理员', operator: '运维操作员', viewer: '只读观察员' }[r] || r || '-'; }
  function fmtTime(v) { if (!v) return '-'; var d = new Date(v); return isNaN(d.getTime()) ? escapeHtml(v) : d.toLocaleString('zh-CN', { hour12: false }); }
  function pagination() { var pages = Math.max(1, Math.ceil(state.total / state.pageSize)); document.getElementById('page-info').textContent = '共 ' + state.total + ' 条 | 第 ' + state.page + '/' + pages + ' 页'; document.getElementById('btn-prev').disabled = state.page <= 1; document.getElementById('btn-next').disabled = state.total === 0 || state.page >= pages; }
  async function loadUsers() {
    hideError(); tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">加载中...</td></tr>';
    try {
      var params = new URLSearchParams({ page: state.page, page_size: state.pageSize });
      var kw = document.getElementById('f-username').value.trim();
      if (kw) params.set('username', kw);
      var data = await api.get('/api/users?' + params.toString());
      state.total = data.total || 0; state.items = data.items || [];
      tbody.innerHTML = state.items.length ? state.items.map(function (u) {
        var isSelf = String(u.id) === String(me.id);
        return '<tr><td>' + escapeHtml(u.id) + '</td><td>' + escapeHtml(u.username) + (isSelf ? ' <span class="badge text-bg-light border">我</span>' : '') + '</td><td><span class="badge ' + (u.role === 'admin' ? 'text-bg-danger' : u.role === 'operator' ? 'text-bg-primary' : 'text-bg-secondary') + '">' + escapeHtml(roleLabel(u.role)) + '</span></td><td><span class="status-badge ' + (u.is_active ? 'status-success' : 'status-disabled') + '">' + (u.is_active ? '启用' : '停用') + '</span></td><td>' + fmtTime(u.last_login_at) + '</td><td>' + fmtTime(u.created_at) + '</td><td class="text-end text-nowrap">' + (isSelf ? '' : '<button class="btn btn-sm btn-outline-primary btn-icon me-1 js-edit" data-id="' + escapeHtml(u.id) + '" title="编辑"><i class="bi bi-pencil"></i></button><button class="btn btn-sm btn-outline-danger btn-icon js-toggle" data-id="' + escapeHtml(u.id) + '" data-active="' + (u.is_active ? '1' : '0') + '" title="' + (u.is_active ? '停用' : '启用') + '"><i class="bi bi-' + (u.is_active ? 'pause' : 'play') + '"></i></button>') + '</td></tr>';
      }).join('') : '<tr><td colspan="7" class="empty-state"><i class="bi bi-people"></i><div>暂无用户</div></td></tr>';
      pagination();
    } catch (err) { tbody.innerHTML = ''; state.total = 0; pagination(); showError('加载用户失败：' + err.message); }
  }
  function openModal(user) {
    hideError(); state.editingId = user ? user.id : null;
    document.getElementById('userModalLabel').textContent = user ? '编辑用户' : '新建用户';
    document.getElementById('u-username').value = user ? user.username : '';
    document.getElementById('u-username').disabled = !!user;
    document.getElementById('u-password').value = '';
    document.getElementById('u-role').value = user ? user.role : 'operator';
    document.getElementById('u-active').checked = user ? !!user.is_active : true;
    document.getElementById('save-text').textContent = user ? '保存' : '创建';
    modal.show();
  }
  document.getElementById('btn-refresh').addEventListener('click', function () { state.page = 1; loadUsers(); });
  document.getElementById('f-username').addEventListener('keydown', function (e) { if (e.key === 'Enter') { state.page = 1; loadUsers(); } });
  document.getElementById('btn-create').addEventListener('click', function () { openModal(null); });
  document.getElementById('btn-save').addEventListener('click', async function () {
    var formError = document.getElementById('form-error');
    formError.classList.add('d-none'); formError.textContent = '';
    var username = document.getElementById('u-username').value.trim();
    var password = document.getElementById('u-password').value;
    var role = document.getElementById('u-role').value;
    var active = document.getElementById('u-active').checked;
    if (!username) { formError.textContent = '请填写用户名'; formError.classList.remove('d-none'); return; }
    var btn = document.getElementById('btn-save'); btn.disabled = true; document.getElementById('save-spin').classList.remove('d-none');
    try {
      if (state.editingId) {
        var body = { role: role, is_active: active };
        if (password) body.password = password;
        await api.put('/api/users/' + encodeURIComponent(state.editingId), body);
      } else {
        if (!password) { formError.textContent = '请填写初始密码'; formError.classList.remove('d-none'); btn.disabled = false; document.getElementById('save-spin').classList.add('d-none'); return; }
        await api.post('/api/users', { username: username, password: password, role: role });
      }
      modal.hide(); loadUsers();
    } catch (err) { formError.textContent = err.message; formError.classList.remove('d-none'); }
    finally { btn.disabled = false; document.getElementById('save-spin').classList.add('d-none'); }
  });
  tbody.addEventListener('click', async function (event) {
    var btn = event.target.closest('button'); if (!btn) return;
    var id = btn.getAttribute('data-id');
    var user = state.items.filter(function (u) { return String(u.id) === id; })[0];
    if (!user) return;
    if (btn.classList.contains('js-edit')) { openModal(user); return; }
    if (btn.classList.contains('js-toggle')) {
      if (!window.confirm('确定' + (user.is_active ? '停用' : '启用') + '用户「' + user.username + '」吗？' + (user.is_active ? '停用后该用户将无法登录。' : ''))) return;
      try { await api.put('/api/users/' + encodeURIComponent(id), { is_active: !user.is_active }); loadUsers(); } catch (err) { showError('操作失败：' + err.message); }
    }
  });
  document.getElementById('btn-prev').addEventListener('click', function () { if (state.page > 1) { state.page--; loadUsers(); } });
  document.getElementById('btn-next').addEventListener('click', function () { if (state.page < Math.ceil(state.total / state.pageSize)) { state.page++; loadUsers(); } });
  loadUsers();
})();