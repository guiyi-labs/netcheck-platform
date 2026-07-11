(function () {
  'use strict';
  if (!Auth.requireAuth()) return;
  Auth.renderNav('app-nav');

  var state = { page: 1, pageSize: 20, total: 0, scans: [], selectedScanId: null, results: [] };
  var scanTbody = document.getElementById('scan-tbody');
  var resultTbody = document.getElementById('result-tbody');
  var scanError = document.getElementById('scan-error');
  var resultError = document.getElementById('result-error');
  var alertBox = document.getElementById('discovery-alert');

  function escapeHtml(value) { return value == null ? '' : String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function showError(el, message) { el.textContent = message; el.classList.remove('d-none'); }
  function hideError(el) { el.textContent = ''; el.classList.add('d-none'); }
  function showAlert(type, message) { alertBox.className = 'alert alert-' + type; alertBox.textContent = message; alertBox.classList.remove('d-none'); }
  function hideAlert() { alertBox.textContent = ''; alertBox.className = 'alert d-none'; }
  function fmtTime(value) { if (!value) return '-'; var date = new Date(value); return isNaN(date.getTime()) ? escapeHtml(value) : date.toLocaleString('zh-CN', { hour12: false }); }
  function statusBadge(status) { var cls = { completed: 'status-success', success: 'status-success', running: 'status-running', pending: 'status-running', failed: 'status-failed', error: 'status-failed' }[status] || 'status-unknown'; return '<span class="status-badge ' + cls + '">' + escapeHtml(status || 'unknown') + '</span>'; }
  function modeLabel(mode) { return { ping_port: 'Ping + 端口', ping: '仅 Ping', port: '仅端口' }[mode] || mode || '-'; }

  function renderScans() {
    document.getElementById('scan-page-info').textContent = '共 ' + state.total + ' 条';
    if (!state.scans.length) { scanTbody.innerHTML = '<tr><td colspan="10" class="empty-state"><i class="bi bi-inbox"></i><div>暂无扫描历史</div></td></tr>'; return; }
    scanTbody.innerHTML = state.scans.map(function (scan) {
      var active = String(scan.id) === String(state.selectedScanId) ? ' class="table-active"' : '';
      return '<tr' + active + '><td>' + escapeHtml(scan.id) + '</td><td class="text-truncate-cell" title="' + escapeHtml(scan.target_range) + '">' + escapeHtml(scan.target_range) + '</td><td>' + escapeHtml(modeLabel(scan.scan_mode)) + '</td><td>' + escapeHtml(scan.ports || '-') + '</td><td>' + statusBadge(scan.status) + '</td><td>' + escapeHtml(scan.total_targets) + '</td><td>' + escapeHtml(scan.discovered_count) + '</td><td class="text-nowrap">' + fmtTime(scan.started_at) + '</td><td class="text-nowrap">' + fmtTime(scan.finished_at) + '</td><td class="text-end"><button class="btn btn-sm btn-outline-primary js-results" data-id="' + escapeHtml(scan.id) + '"><i class="bi bi-list-ul me-1"></i>查看结果</button></td></tr>';
    }).join('');
  }

  function renderResults() {
    if (!state.selectedScanId) { resultTbody.innerHTML = '<tr><td colspan="9" class="empty-state"><i class="bi bi-search"></i><div>请选择扫描记录查看结果</div></td></tr>'; document.getElementById('result-title').textContent = '请选择一次扫描查看结果'; return; }
    document.getElementById('result-title').textContent = '扫描 #' + state.selectedScanId + '，共 ' + state.results.length + ' 条结果';
    if (!state.results.length) { resultTbody.innerHTML = '<tr><td colspan="9" class="empty-state"><i class="bi bi-inbox"></i><div>该扫描暂无发现结果</div></td></tr>'; return; }
    resultTbody.innerHTML = state.results.map(function (item) {
      var imported = item.imported_asset_id || item.matched_asset_id;
      var disabled = imported ? ' disabled' : '';
      var buttonText = imported ? '已导入' : '导入资产';
      return '<tr><td>' + escapeHtml(item.id) + '</td><td>' + escapeHtml(item.ip) + '</td><td>' + escapeHtml(item.hostname || '-') + '</td><td>' + escapeHtml(item.open_ports || '-') + '</td><td>' + statusBadge(item.status) + '</td><td>' + (item.already_exists ? ('#' + escapeHtml(item.matched_asset_id || '-')) : '-') + '</td><td>' + (item.imported_asset_id ? ('#' + escapeHtml(item.imported_asset_id)) : '-') + '</td><td class="text-nowrap">' + fmtTime(item.created_at) + '</td><td class="text-end"><button class="btn btn-sm btn-outline-success js-import" data-id="' + escapeHtml(item.id) + '"' + disabled + '>' + buttonText + '</button></td></tr>';
    }).join('');
  }

  async function loadScans() {
    hideError(scanError); hideAlert(); scanTbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted py-4">加载中...</td></tr>';
    try { var data = await api.get('/api/discovery/scans?page=' + state.page + '&page_size=' + state.pageSize); state.total = data && data.total || 0; state.scans = data && data.items || []; renderScans(); }
    catch (err) { state.scans = []; state.total = 0; scanTbody.innerHTML = ''; showError(scanError, '加载扫描历史失败：' + err.message); document.getElementById('scan-page-info').textContent = '共 0 条'; }
  }

  async function loadResults(scanId) {
    state.selectedScanId = scanId; state.results = []; hideError(resultError); renderScans(); resultTbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-4">加载结果中...</td></tr>'; document.getElementById('result-title').textContent = '扫描 #' + scanId + ' 加载中...';
    try { var data = await api.get('/api/discovery/scans/' + encodeURIComponent(scanId) + '/results?page=1&page_size=200'); state.results = data && data.items || []; renderResults(); }
    catch (err) { state.results = []; resultTbody.innerHTML = ''; showError(resultError, '加载扫描结果失败：' + err.message); document.getElementById('result-title').textContent = '扫描 #' + scanId + ' 结果加载失败'; }
  }

  document.getElementById('scan-form').addEventListener('submit', async function (event) {
    event.preventDefault(); hideAlert(); hideError(scanError);
    var body = { target_range: document.getElementById('target-range').value.trim(), scan_mode: document.getElementById('scan-mode').value, ports: document.getElementById('scan-ports').value.trim() || null };
    if (!body.target_range) { showAlert('danger', '请填写目标范围'); return; }
    var button = document.getElementById('btn-start-scan'); button.disabled = true; document.getElementById('scan-spin').classList.remove('d-none');
    try { var scan = await api.post('/api/discovery/scans', body); showAlert('success', '扫描已完成，扫描 #' + scan.id + ' 发现 ' + (scan.discovered_count || 0) + ' 个目标。'); state.page = 1; await loadScans(); await loadResults(scan.id); }
    catch (err) { showAlert('danger', '扫描失败：' + err.message); }
    finally { button.disabled = false; document.getElementById('scan-spin').classList.add('d-none'); }
  });

  scanTbody.addEventListener('click', function (event) { var btn = event.target.closest('.js-results'); if (btn) loadResults(btn.getAttribute('data-id')); });
  resultTbody.addEventListener('click', async function (event) { var btn = event.target.closest('.js-import'); if (!btn || btn.disabled) return; btn.disabled = true; var id = btn.getAttribute('data-id'); try { await api.post('/api/discovery/results/' + encodeURIComponent(id) + '/import'); showAlert('success', '导入成功，结果已刷新。'); await loadResults(state.selectedScanId); } catch (err) { btn.disabled = false; showError(resultError, '导入失败：' + err.message); } });
  document.getElementById('btn-refresh-scans').addEventListener('click', loadScans);
  loadScans();
})();
