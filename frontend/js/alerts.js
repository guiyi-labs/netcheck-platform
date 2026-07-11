(function () {
  'use strict';
  if (!Auth.requireAuth()) return;
  Auth.renderNav('app-nav');

  var state = { page: 1, pageSize: 20, total: 0, items: [] };
  var tbody = document.getElementById('alerts-tbody');
  var errorBox = document.getElementById('page-error');
  var successBox = document.getElementById('page-success');
  var detailModal = new bootstrap.Modal(document.getElementById('detailModal'));
  var filters = { alert_status: 'f-status', alert_level: 'f-level', asset_id: 'f-asset-id', check_type: 'f-check-type', fault_type: 'f-fault-type' };

  function escapeHtml(v) { return v == null ? '' : String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function value(id) { return document.getElementById(id).value.trim(); }
  function setText(id, v) { var el = document.getElementById(id); if (el) el.textContent = v == null ? '--' : v; }
  function showError(msg) { errorBox.textContent = msg; errorBox.classList.remove('d-none'); }
  function hideError() { errorBox.textContent = ''; errorBox.classList.add('d-none'); }
  function showSuccess(msg) { successBox.textContent = msg; successBox.classList.remove('d-none'); window.setTimeout(function () { successBox.classList.add('d-none'); }, 2500); }
  function hideSuccess() { successBox.textContent = ''; successBox.classList.add('d-none'); }
  function time(v) { if (!v) return '-'; var d = new Date(v); return isNaN(d.getTime()) ? escapeHtml(v) : d.toLocaleString('zh-CN', { hour12: false }); }
  function levelLabel(v) { return { critical: '严重', major: '重要', warning: '警告', minor: '轻微' }[v] || v || '-'; }
  function levelClass(v) { return { critical: 'alert-level-critical', major: 'alert-level-major', warning: 'alert-level-warning', minor: 'alert-level-minor' }[v] || 'status-unknown'; }
  function statusLabel(v) { return { active: '活跃', confirmed: '已确认', recovered: '已恢复' }[v] || v || '-'; }
  function statusClass(v) { return { active: 'alert-status-active', confirmed: 'alert-status-confirmed', recovered: 'alert-status-recovered' }[v] || 'status-unknown'; }
  function checkTypeLabel(v) { return { ping: 'Ping', port: '端口', http: 'HTTP' }[v] || v || '-'; }
  function canConfirm(item) { return item && item.alert_status === 'active' && !item.confirmed_at; }
  function canRecover(item) { return item && item.alert_status !== 'recovered'; }
  function setButtonLoading(button, loadingText) { button.disabled = true; button.dataset.oldHtml = button.innerHTML; button.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>' + escapeHtml(loadingText); }
  function restoreButton(button) { button.disabled = false; if (button.dataset.oldHtml) button.innerHTML = button.dataset.oldHtml; }

  function buildUrl() {
    var params = new URLSearchParams({ page: String(state.page), page_size: String(state.pageSize) });
    Object.keys(filters).forEach(function (key) { var v = value(filters[key]); if (v) params.set(key, v); });
    return '/api/alerts?' + params.toString();
  }

  async function loadSummary() {
    try {
      var summary = await api.get('/api/alerts/summary');
      setText('stat-active-alerts', summary && summary.active_alerts);
      setText('stat-unconfirmed-alerts', summary && summary.unconfirmed_alerts);
      setText('stat-recovered-alerts-today', summary && summary.recovered_alerts_today);
    } catch (err) {
      setText('stat-active-alerts', '--');
      setText('stat-unconfirmed-alerts', '--');
      setText('stat-recovered-alerts-today', '--');
      showError('告警统计加载失败：' + (err.message || err));
    }
  }

  async function loadPolicy() {
    var status = document.getElementById('policy-status');
    status.textContent = '读取中...';
    try {
      var p = await api.get('/api/alert-policy');
      document.getElementById('policy-name').value = p && p.name || '';
      document.getElementById('policy-enabled').checked = !!(p && p.enabled);
      document.getElementById('policy-slow-response').value = p && p.slow_response_threshold != null ? p.slow_response_threshold : '';
      document.getElementById('policy-failure').value = p && p.failure_threshold != null ? p.failure_threshold : '';
      document.getElementById('policy-recovery').value = p && p.recovery_threshold != null ? p.recovery_threshold : '';
      document.getElementById('policy-deduplicate').checked = !!(p && p.deduplicate_enabled);
      status.textContent = '已读取';
    } catch (err) {
      status.textContent = '读取失败';
      showError('告警策略加载失败：' + (err.message || err));
    }
  }

  async function savePolicy() {
    hideError(); hideSuccess();
    var button = document.getElementById('btn-policy-save');
    setButtonLoading(button, '保存中');
    try {
      await api.put('/api/alert-policy', {
        name: value('policy-name'),
        enabled: document.getElementById('policy-enabled').checked,
        slow_response_threshold: Number(value('policy-slow-response') || 0),
        failure_threshold: Number(value('policy-failure') || 0),
        recovery_threshold: Number(value('policy-recovery') || 0),
        deduplicate_enabled: document.getElementById('policy-deduplicate').checked
      });
      document.getElementById('policy-status').textContent = '已保存';
      showSuccess('告警策略保存成功');
    } catch (err) {
      showError('告警策略保存失败：' + (err.message || err));
    } finally {
      restoreButton(button);
    }
  }

  async function loadAlerts() {
    hideError(); hideSuccess();
    tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-4"><span class="spinner-border spinner-border-sm me-1"></span>加载中...</td></tr>';
    try {
      var data = await api.get(buildUrl());
      state.total = data && data.total || 0;
      state.items = data && data.items || [];
      renderTable();
      document.getElementById('alerts-updated').textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
    } catch (err) {
      state.total = 0; state.items = [];
      setText('stat-total-alerts', 0);
      tbody.innerHTML = '<tr><td colspan="9" class="empty-state"><i class="bi bi-exclamation-circle"></i><div>告警加载失败</div></td></tr>';
      showError('告警列表加载失败：' + (err.message || err));
      renderPager();
    }
  }

  function renderTable() {
    setText('stat-total-alerts', state.total);
    if (!state.items.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty-state"><i class="bi bi-inbox"></i><div>暂无符合条件的告警</div></td></tr>';
      renderPager();
      return;
    }
    tbody.innerHTML = state.items.map(function (item, index) {
      var title = item.alert_title || ('告警 #' + item.id);
      var confirmDisabled = canConfirm(item) ? '' : ' disabled';
      var recoverDisabled = canRecover(item) ? '' : ' disabled';
      return '<tr>' +
        '<td>' + escapeHtml(item.id) + '</td>' +
        '<td><div class="fw-semibold text-truncate-cell" title="' + escapeHtml(title) + '">' + escapeHtml(title) + '</div><div class="text-muted small text-truncate-cell" title="' + escapeHtml(item.alert_key || '') + '">' + escapeHtml(item.alert_key || '-') + '</div></td>' +
        '<td><span class="status-badge ' + levelClass(item.alert_level) + '">' + escapeHtml(levelLabel(item.alert_level)) + '</span></td>' +
        '<td><span class="status-badge ' + statusClass(item.alert_status) + '">' + escapeHtml(statusLabel(item.alert_status)) + '</span></td>' +
        '<td>' + escapeHtml(item.asset_id == null ? '-' : item.asset_id) + '</td>' +
        '<td><div>' + escapeHtml(checkTypeLabel(item.check_type)) + '</div><div class="text-muted small">' + escapeHtml(item.fault_type || '-') + '</div></td>' +
        '<td>' + escapeHtml(item.trigger_count == null ? '-' : item.trigger_count) + '<div class="text-muted small">失败 ' + escapeHtml(item.consecutive_failures == null ? '-' : item.consecutive_failures) + ' / 成功 ' + escapeHtml(item.consecutive_successes == null ? '-' : item.consecutive_successes) + '</div></td>' +
        '<td class="text-nowrap">' + time(item.last_triggered_at) + '</td>' +
        '<td class="text-end text-nowrap"><button class="btn btn-sm btn-outline-primary js-detail" data-index="' + index + '">详情</button> <button class="btn btn-sm btn-outline-success js-confirm" data-index="' + index + '"' + confirmDisabled + '>确认</button> <button class="btn btn-sm btn-outline-warning js-recover" data-index="' + index + '"' + recoverDisabled + '>恢复</button></td>' +
        '</tr>';
    }).join('');
    renderPager();
  }

  function renderPager() {
    var pages = Math.max(1, Math.ceil(state.total / state.pageSize));
    document.getElementById('page-info').textContent = '共 ' + state.total + ' 条 | 第 ' + state.page + '/' + pages + ' 页';
    document.getElementById('btn-prev').disabled = state.page <= 1;
    document.getElementById('btn-next').disabled = state.total === 0 || state.page >= pages;
  }

  async function confirmAlert(item, button) {
    if (!item) return;
    hideError(); hideSuccess(); setButtonLoading(button, '确认中');
    try {
      await api.post('/api/alerts/' + encodeURIComponent(item.id) + '/confirm', {});
      await refreshAll();
      showSuccess('告警确认成功');
    } catch (err) {
      showError('告警确认失败：' + (err.message || err));
    } finally {
      restoreButton(button);
    }
  }

  async function recoverAlert(item, button) {
    if (!item) return;
    var reason = prompt('请输入恢复原因（留空将使用默认原因）', '手动恢复');
    if (reason === null) return;
    reason = reason.trim() || '手动恢复';
    hideError(); hideSuccess(); setButtonLoading(button, '恢复中');
    try {
      await api.post('/api/alerts/' + encodeURIComponent(item.id) + '/recover', { recovery_reason: reason });
      await refreshAll();
      showSuccess('告警恢复成功');
    } catch (err) {
      showError('告警恢复失败：' + (err.message || err));
    } finally {
      restoreButton(button);
    }
  }

  async function showDetail(item) {
    if (!item) return;
    var detailError = document.getElementById('detail-error');
    var loading = document.getElementById('detail-loading');
    var content = document.getElementById('detail-content');
    detailError.classList.add('d-none');
    content.innerHTML = '';
    loading.classList.remove('d-none');
    detailModal.show();
    try {
      var data = await api.get('/api/alerts/' + encodeURIComponent(item.id));
      loading.classList.add('d-none');
      renderDetail(data || item);
    } catch (err) {
      loading.classList.add('d-none');
      detailError.textContent = '详情加载失败：' + (err.message || err);
      detailError.classList.remove('d-none');
      renderDetail(item);
    }
  }

  function renderDetail(item) {
    var rows = [
      ['告警 ID', item.id], ['标题', item.alert_title], ['等级', levelLabel(item.alert_level)], ['状态', statusLabel(item.alert_status)],
      ['资产 ID', item.asset_id], ['运行 ID', item.run_id], ['结果 ID', item.result_id], ['诊断 ID', item.diagnosis_id],
      ['告警键', item.alert_key], ['检测类型', checkTypeLabel(item.check_type)], ['故障类型', item.fault_type],
      ['证据', item.evidence], ['建议', item.suggestion], ['首次触发', time(item.first_triggered_at)], ['最近触发', time(item.last_triggered_at)],
      ['触发次数', item.trigger_count], ['连续失败', item.consecutive_failures], ['连续成功', item.consecutive_successes],
      ['确认人', item.confirmed_by], ['确认时间', time(item.confirmed_at)], ['恢复时间', time(item.recovered_at)], ['恢复原因', item.recovery_reason],
      ['创建时间', time(item.created_at)], ['更新时间', time(item.updated_at)]
    ];
    document.getElementById('detail-content').innerHTML = rows.map(function (row) {
      return '<dt class="col-sm-3">' + escapeHtml(row[0]) + '</dt><dd class="col-sm-9 text-break">' + escapeHtml(row[1] == null || row[1] === '' ? '-' : row[1]) + '</dd>';
    }).join('');
  }

  async function refreshAll() {
    await Promise.all([loadSummary(), loadAlerts()]);
  }

  document.getElementById('filter-form').addEventListener('submit', function (event) { event.preventDefault(); state.page = 1; refreshAll(); });
  document.getElementById('btn-reset').addEventListener('click', function () { Object.keys(filters).forEach(function (key) { document.getElementById(filters[key]).value = ''; }); state.page = 1; refreshAll(); });
  document.getElementById('btn-prev').addEventListener('click', function () { if (state.page > 1) { state.page--; loadAlerts(); } });
  document.getElementById('btn-next').addEventListener('click', function () { if (state.page < Math.ceil(state.total / state.pageSize)) { state.page++; loadAlerts(); } });
  document.getElementById('btn-refresh').addEventListener('click', refreshAll);
  document.getElementById('btn-policy-reload').addEventListener('click', function () { hideError(); loadPolicy(); });
  document.getElementById('policy-form').addEventListener('submit', function (event) { event.preventDefault(); savePolicy(); });
  tbody.addEventListener('click', function (event) {
    var detail = event.target.closest('.js-detail');
    var confirm = event.target.closest('.js-confirm');
    var recover = event.target.closest('.js-recover');
    if (detail) showDetail(state.items[Number(detail.getAttribute('data-index'))]);
    if (confirm) confirmAlert(state.items[Number(confirm.getAttribute('data-index'))], confirm);
    if (recover) recoverAlert(state.items[Number(recover.getAttribute('data-index'))], recover);
  });

  loadPolicy();
  refreshAll();
})();
