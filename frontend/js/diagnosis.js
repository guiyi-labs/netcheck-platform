(function () {
  'use strict';
  if (!Auth.requireAuth()) return;
  Auth.renderNav('app-nav');

  var urlParams = new URLSearchParams(location.search);
  var urlRunId = urlParams.get('run_id') || '';
  var state = { page: 1, pageSize: 20, total: 0, items: [], assets: {} };
  var tbody = document.getElementById('diagnosis-tbody');
  var error = document.getElementById('page-error');
  var message = document.getElementById('page-message');
  var detailModal = new bootstrap.Modal(document.getElementById('detailModal'));

  function escapeHtml(v) { return v == null ? '' : String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function showError(msg) { error.textContent = msg; error.classList.remove('d-none'); }
  function hideError() { error.textContent = ''; error.classList.add('d-none'); }
  function showMessage(msg) { message.textContent = msg; message.classList.remove('d-none'); }
  function hideMessage() { message.textContent = ''; message.classList.add('d-none'); }
  function time(value) { if (!value) return '-'; var d = new Date(value); return isNaN(d.getTime()) ? escapeHtml(value) : d.toLocaleString('zh-CN', { hour12: false }); }
  function typeLabel(type) { return { ping: 'Ping', port: '端口', http: 'HTTP' }[type] || type || '-'; }
  function severityLabel(severity) { return { critical: 'Critical', major: 'Major', minor: 'Minor', warning: 'Warning' }[severity] || severity || '-'; }
  function severityClass(severity) { return { critical: 'severity-critical', major: 'severity-major', minor: 'severity-minor', warning: 'severity-warning' }[severity] || 'status-unknown'; }
  function assetName(assetId) { return state.assets[String(assetId)] || ('资产 #' + assetId); }
  function valueOrDash(value) { return value == null || value === '' ? '-' : value; }

  function buildQuery() {
    var params = new URLSearchParams();
    params.set('page', state.page);
    params.set('page_size', state.pageSize);
    [['run_id', 'f-run-id'], ['asset_id', 'f-asset-id'], ['severity', 'f-severity'], ['check_type', 'f-check-type'], ['fault_type', 'f-fault-type']].forEach(function (pair) {
      var value = document.getElementById(pair[1]).value.trim();
      if (value) params.set(pair[0], value);
    });
    return params.toString();
  }

  async function loadAssets() {
    var select = document.getElementById('f-asset-id');
    try {
      var data = await api.get('/api/assets?page=1&page_size=100');
      var items = data && data.items || [];
      items.forEach(function (asset) {
        var label = asset.name || asset.ip || ('资产 #' + asset.id);
        state.assets[String(asset.id)] = label;
      });
      select.innerHTML = '<option value="">全部</option>' + items.map(function (asset) {
        var label = asset.name || asset.ip || ('资产 #' + asset.id);
        return '<option value="' + escapeHtml(asset.id) + '">' + escapeHtml(label) + '</option>';
      }).join('');
    } catch (err) {
      select.innerHTML = '<option value="">全部</option>';
    }
  }

  function setStats(total, critical, major, warning) {
    document.getElementById('stat-total').textContent = total;
    document.getElementById('stat-critical').textContent = critical;
    document.getElementById('stat-major').textContent = major;
    document.getElementById('stat-warning').textContent = warning;
  }

  function buildStatsQuery(severity) {
    var params = new URLSearchParams(buildQuery());
    params.set('page', 1);
    params.set('page_size', 1);
    params.delete('severity');
    if (severity) params.set('severity', severity);
    return params.toString();
  }

  async function loadStats(total) {
    try {
      var results = await Promise.all(['critical', 'major', 'warning'].map(function (severity) {
        return api.get('/api/diagnosis?' + buildStatsQuery(severity));
      }));
      setStats(total, results[0] && results[0].total || 0, results[1] && results[1].total || 0, results[2] && results[2].total || 0);
    } catch (err) {
      setStats(total, '--', '--', '--');
    }
  }

  function renderRows() {
    if (!state.items.length) {
      tbody.innerHTML = '<tr><td colspan="10" class="empty-state"><i class="bi bi-inbox"></i><div>暂无符合条件的诊断记录</div></td></tr>';
    } else {
      tbody.innerHTML = state.items.map(function (item, index) {
        var evidence = valueOrDash(item.evidence), suggestion = valueOrDash(item.suggestion);
        return '<tr>' +
          '<td>' + escapeHtml(item.id) + '</td>' +
          '<td>' + escapeHtml(item.run_id) + '</td>' +
          '<td>' + escapeHtml(assetName(item.asset_id)) + '</td>' +
          '<td>' + escapeHtml(typeLabel(item.check_type)) + '</td>' +
          '<td>' + escapeHtml(valueOrDash(item.fault_type)) + '</td>' +
          '<td><span class="status-badge ' + severityClass(item.severity) + '">' + escapeHtml(severityLabel(item.severity)) + '</span></td>' +
          '<td class="diagnosis-evidence text-truncate-cell" title="' + escapeHtml(evidence) + '">' + escapeHtml(evidence) + '</td>' +
          '<td class="diagnosis-suggestion text-truncate-cell" title="' + escapeHtml(suggestion) + '">' + escapeHtml(suggestion) + '</td>' +
          '<td>' + time(item.created_at) + '</td>' +
          '<td class="text-end"><button class="btn btn-sm btn-outline-primary js-detail" data-index="' + index + '">详情</button></td>' +
        '</tr>';
      }).join('');
    }
    var pages = Math.max(1, Math.ceil(state.total / state.pageSize));
    document.getElementById('page-info').textContent = '共 ' + state.total + ' 条 | 第 ' + state.page + '/' + pages + ' 页';
    document.getElementById('btn-prev').disabled = state.page <= 1;
    document.getElementById('btn-next').disabled = state.total === 0 || state.page >= pages;
  }

  async function loadDiagnosis() {
    hideError();
    hideMessage();
    tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted py-4">加载中...</td></tr>';
    try {
      var data = await api.get('/api/diagnosis?' + buildQuery());
      state.items = data && data.items || [];
      state.total = data && typeof data.total === 'number' ? data.total : state.items.length;
      setStats(state.total, '--', '--', '--');
      loadStats(state.total);
      renderRows();
    } catch (err) {
      state.items = [];
      state.total = 0;
      setStats(0, 0, 0, 0);
      tbody.innerHTML = '<tr><td colspan="10" class="empty-state"><i class="bi bi-exclamation-circle"></i><div>诊断记录加载失败</div></td></tr>';
      document.getElementById('page-info').textContent = '共 0 条 | 第 1/1 页';
      document.getElementById('btn-prev').disabled = true;
      document.getElementById('btn-next').disabled = true;
      showError('加载故障诊断失败：' + err.message);
    }
  }

  async function showDetail(item) {
    try {
      item = await api.get('/api/diagnosis/' + encodeURIComponent(item.id));
    } catch (err) {}
    var rows = [
      ['诊断 ID', item.id], ['运行 ID', item.run_id], ['结果 ID', item.result_id], ['资产', assetName(item.asset_id)], ['资产 ID', item.asset_id],
      ['检测类型', typeLabel(item.check_type)], ['故障类型', item.fault_type], ['等级', severityLabel(item.severity)], ['证据', item.evidence], ['建议', item.suggestion], ['创建时间', time(item.created_at)]
    ];
    document.getElementById('detail-content').innerHTML = rows.map(function (row) {
      return '<dt class="col-sm-3">' + escapeHtml(row[0]) + '</dt><dd class="col-sm-9 text-break">' + escapeHtml(valueOrDash(row[1])) + '</dd>';
    }).join('');
    detailModal.show();
  }

  async function regenerate() {
    if (!urlRunId) return;
    var btn = document.getElementById('btn-regenerate');
    hideError();
    hideMessage();
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>生成中...';
    try {
      await api.post('/api/diagnosis/runs/' + encodeURIComponent(urlRunId) + '/generate', {});
      showMessage('已触发本次运行的诊断重新生成。');
      state.page = 1;
      loadDiagnosis();
    } catch (err) {
      showError('重新生成失败：' + err.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i>重新生成';
    }
  }

  if (urlRunId) {
    document.getElementById('f-run-id').value = urlRunId;
    document.getElementById('run-caption').textContent = '运行 ID：' + urlRunId;
    document.getElementById('btn-regenerate').classList.remove('d-none');
  }

  document.getElementById('filter-form').addEventListener('submit', function (event) { event.preventDefault(); state.page = 1; loadDiagnosis(); });
  document.getElementById('btn-reset').addEventListener('click', function () { ['f-run-id', 'f-asset-id', 'f-check-type', 'f-severity', 'f-fault-type'].forEach(function (id) { document.getElementById(id).value = ''; }); state.page = 1; loadDiagnosis(); });
  document.getElementById('btn-refresh').addEventListener('click', function () { loadDiagnosis(); });
  document.getElementById('btn-regenerate').addEventListener('click', regenerate);
  document.getElementById('btn-prev').addEventListener('click', function () { if (state.page > 1) { state.page--; loadDiagnosis(); } });
  document.getElementById('btn-next').addEventListener('click', function () { if (state.page < Math.ceil(state.total / state.pageSize)) { state.page++; loadDiagnosis(); } });
  tbody.addEventListener('click', function (event) { var button = event.target.closest('.js-detail'); if (button) showDetail(state.items[Number(button.getAttribute('data-index'))]); });

  loadAssets().then(loadDiagnosis);
})();
