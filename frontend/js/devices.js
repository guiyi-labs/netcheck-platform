/**
 * 设备管理页：SNMPv3 / SSH 只读采集（N1）。
 * - 设备 CRUD、凭据管理（加密存储，不显示密钥）
 * - 触发采集、查看接口指标与速率
 * - 空样本显示 unknown/unavailable，不用 0 或绿色代替
 */
(function () {
  'use strict';
  if (!Auth.requireAuth()) return;
  Auth.renderNav('app-nav');

  var state = { page: 1, pageSize: 20, total: 0, items: [], credentials: [] };
  var tbody = document.getElementById('device-tbody');
  var listError = document.getElementById('list-error');
  var deviceModal = new bootstrap.Modal(document.getElementById('deviceModal'));
  var credModal = new bootstrap.Modal(document.getElementById('credModal'));
  var ifModal = new bootstrap.Modal(document.getElementById('ifModal'));
  var isAdmin = Auth.user && Auth.user() && Auth.user().role === 'admin';

  function escapeHtml(value) {
    return value == null ? ''
      : String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function showError(el, message) { if (!el) return; el.textContent = message; el.classList.remove('d-none'); }
  function hideError(el) { if (!el) return; el.textContent = ''; el.classList.add('d-none'); }
  function fmtTime(value) {
    if (!value) return '-';
    var date = new Date(value);
    return isNaN(date.getTime()) ? escapeHtml(value) : date.toLocaleString('zh-CN', { hour12: false });
  }
  var STATUS_LABEL = {
    idle: '未采集', collecting: '采集中', success: '成功',
    failed: '失败', error: '错误', auth_failed: '认证失败',
    priv_failed: '密钥错误', timeout: '超时', conn_refused: '连接拒绝',
    host_key_unknown: 'HostKey 未知', host_key_mismatch: 'HostKey 不匹配',
  };
  var STATUS_CLASS = {
    idle: 'status-disabled', collecting: 'status-running', success: 'status-success',
    failed: 'status-danger', error: 'status-danger', auth_failed: 'status-danger',
    priv_failed: 'status-danger', timeout: 'status-warning', conn_refused: 'status-warning',
    host_key_unknown: 'status-warning', host_key_mismatch: 'status-danger',
  };
  function statusBadge(status) {
    var cls = STATUS_CLASS[status] || 'status-disabled';
    var label = STATUS_LABEL[status] || escapeHtml(status || 'unknown');
    return '<span class="status-badge ' + cls + '">' + label + '</span>';
  }
  function rateText(bps) {
    if (bps == null) return '<span class="text-muted">unknown</span>';
    if (bps === 0) return '0 bps';
    if (bps >= 1e9) return (bps / 1e9).toFixed(2) + ' Gbps';
    if (bps >= 1e6) return (bps / 1e6).toFixed(2) + ' Mbps';
    if (bps >= 1e3) return (bps / 1e3).toFixed(2) + ' kbps';
    return bps.toFixed(1) + ' bps';
  }
  function renderPagination() {
    var pages = Math.max(1, Math.ceil(state.total / state.pageSize));
    document.getElementById('page-info').textContent = '共 ' + state.total + ' 台 | 第 ' + state.page + '/' + pages + ' 页';
    document.getElementById('btn-prev').disabled = state.page <= 1;
    document.getElementById('btn-next').disabled = state.total === 0 || state.page >= pages;
  }
  function renderDevices() {
    if (!state.items.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty-state"><i class="bi bi-router"></i><div>暂无设备。点击「新增设备」录入管理 IP 与凭据。</div></td></tr>';
      return;
    }
    tbody.innerHTML = state.items.map(function (device) {
      var protocols = [];
      if (device.has_snmp) protocols.push('<span class="badge text-bg-light border me-1">SNMPv3</span>');
      if (device.has_ssh) protocols.push('<span class="badge text-bg-light border me-1">SSH</span>');
      var protocolText = protocols.join('') || '<span class="text-muted">-</span>';
      var fact = device.sys_name || device.hostname || '';
      return '<tr>' +
        '<td><input type="checkbox" class="js-check" data-id="' + device.id + '" /></td>' +
        '<td>' + escapeHtml(device.name) + '</td>' +
        '<td><code>' + escapeHtml(device.management_ip) + '</code></td>' +
        '<td>' + escapeHtml(device.vendor_platform || 'generic') + '</td>' +
        '<td>' + protocolText + '</td>' +
        '<td>' + statusBadge(device.collect_status) +
          (device.last_collect_error ? '<div class="small text-danger mt-1" title="' + escapeHtml(device.last_collect_error) + '">' + escapeHtml(device.last_collect_error) + '</div>' : '') +
        '</td>' +
        '<td class="text-truncate-cell" title="' + escapeHtml(fact) + '">' + escapeHtml(fact || '-') + '</td>' +
        '<td class="text-nowrap">' + fmtTime(device.last_collected_at) + '</td>' +
        '<td class="text-end text-nowrap">' +
          '<button class="btn btn-sm btn-outline-success btn-icon me-1 js-collect" data-id="' + device.id + '" title="采集"><i class="bi bi-play-fill"></i></button>' +
          (device.has_snmp ? '<button class="btn btn-sm btn-outline-primary btn-icon me-1 js-interfaces" data-id="' + device.id + '" data-name="' + escapeHtml(device.name) + '" title="接口指标"><i class="bi bi-activity"></i></button>' : '') +
          '<button class="btn btn-sm btn-outline-info btn-icon me-1 js-config" data-id="' + device.id + '" data-name="' + escapeHtml(device.name) + '" title="配置备份与差异"><i class="bi bi-file-earmark-code"></i></button>' +
          '<button class="btn btn-sm btn-outline-secondary btn-icon me-1 js-edit" data-id="' + device.id + '" title="编辑"><i class="bi bi-pencil"></i></button>' +
          '<button class="btn btn-sm btn-outline-danger btn-icon js-delete" data-id="' + device.id + '" title="删除"><i class="bi bi-trash"></i></button>' +
        '</td></tr>';
    }).join('');
  }
  async function loadDevices() {
    hideError(listError);
    tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-4">加载中...</td></tr>';
    try {
      var vendor = document.getElementById('f-vendor').value;
      var url = '/api/devices?page=' + state.page + '&page_size=' + state.pageSize;
      if (vendor) url += '&vendor=' + encodeURIComponent(vendor);
      var data = await api.get(url);
      state.total = data && data.total || 0;
      state.items = data && data.items || [];
      renderDevices();
    } catch (err) {
      state.total = 0; state.items = [];
      tbody.innerHTML = '';
      showError(listError, '加载设备失败：' + err.message);
    }
    renderPagination();
  }
  async function loadCredentials() {
    try {
      var data = await api.get('/api/devices/credentials?page=1&page_size=100');
      state.credentials = data && data.items || [];
      var snmpSelect = document.getElementById('m-snmp-cred');
      var sshSelect = document.getElementById('m-ssh-cred');
      var snmpOpts = '<option value="">未配置</option>';
      var sshOpts = '<option value="">未配置</option>';
      state.credentials.forEach(function (cred) {
        var label = escapeHtml(cred.name) + ' (' + escapeHtml(cred.username) + ')';
        if (cred.protocol === 'snmp_v3') snmpOpts += '<option value="' + cred.id + '">' + label + '</option>';
        else sshOpts += '<option value="' + cred.id + '">' + label + '</option>';
      });
      snmpSelect.innerHTML = snmpOpts;
      sshSelect.innerHTML = sshOpts;
    } catch (err) {
      showError(listError, '加载凭据失败：' + err.message);
    }
  }
  function openDeviceModal(device) {
    hideError(document.getElementById('form-error'));
    document.getElementById('device-form').reset();
    document.getElementById('device-id').value = device ? device.id : '';
    document.getElementById('deviceModalLabel').textContent = device ? '编辑设备' : '新增设备';
    document.getElementById('save-text').textContent = device ? '保存' : '新建';
    document.getElementById('m-name').value = device ? device.name : '';
    document.getElementById('m-ip').value = device ? device.management_ip : '';
    document.getElementById('m-vendor').value = device ? (device.vendor_platform || 'generic') : 'linux';
    document.getElementById('m-snmp-cred').value = device ? (device.snmp_config_id || '') : '';
    document.getElementById('m-ssh-cred').value = device ? (device.ssh_config_id || '') : '';
    deviceModal.show();
  }
  async function openCredModal() {
    hideError(document.getElementById('cred-error'));
    renderCredentials();
    deviceModal.hide();
    credModal.show();
  }
  function renderCredentials() {
    var tbody2 = document.getElementById('cred-tbody');
    if (!state.credentials.length) {
      tbody2.innerHTML = '<tr><td colspan="7" class="empty-state"><i class="bi bi-key"></i><div>暂无凭据</div></td></tr>';
      return;
    }
    tbody2.innerHTML = state.credentials.map(function (cred) {
      var algo = cred.protocol === 'snmp_v3'
        ? escapeHtml((cred.auth_algorithm || 'SHA-256') + ' / ' + (cred.priv_algorithm || 'AES-128'))
        : '-';
      return '<tr>' +
        '<td>' + escapeHtml(cred.name) + '</td>' +
        '<td>' + escapeHtml(cred.protocol === 'snmp_v3' ? 'SNMPv3' : 'SSH') + '</td>' +
        '<td>' + escapeHtml(cred.username) + '</td>' +
        '<td>' + algo + '</td>' +
        '<td>' + (cred.has_secret ? '<span class="badge text-bg-success">已配置</span>' : '<span class="badge text-bg-secondary">未配置</span>') + '</td>' +
        '<td class="text-truncate-cell" title="' + escapeHtml(cred.external_secret_ref || '') + '">' + escapeHtml(cred.external_secret_ref || '-') + '</td>' +
        '<td class="text-end">' + (isAdmin
          ? '<button class="btn btn-sm btn-outline-danger btn-icon js-del-cred" data-id="' + cred.id + '" title="删除"><i class="bi bi-trash"></i></button>'
          : '-') + '</td></tr>';
    }).join('');
  }
  function resetCredForm() {
    document.getElementById('cred-form').reset();
    var protocol = document.getElementById('c-protocol').value;
    toggleCredFields(protocol);
  }
  function toggleCredFields(protocol) {
    var isSnmp = protocol === 'snmp_v3';
    document.getElementById('c-algo-col').classList.toggle('d-none', !isSnmp);
    document.getElementById('c-priv-col').classList.toggle('d-none', !isSnmp);
    document.getElementById('c-pass-col').classList.toggle('d-none', isSnmp);
  }
  async function saveCredential() {
    var formError = document.getElementById('cred-error');
    hideError(formError);
    var protocol = document.getElementById('c-protocol').value;
    var name = document.getElementById('c-name').value.trim();
    var username = document.getElementById('c-username').value.trim();
    if (!name || !username) return showError(formError, '请填写凭据名称与用户名');
    var algo = document.getElementById('c-algo').value;
    if (protocol === 'snmp_v3') {
      var auth = document.getElementById('c-auth').value;
      var priv = document.getElementById('c-priv').value;
      if (!auth || !priv) return showError(formError, 'SNMPv3 需要认证密钥和隐私密钥');
      algo = algo === 'AES-256' ? 'AES-256' : (algo === 'SHA' ? 'SHA' : 'SHA-256');
      var privAlgo = algo === 'AES-256' ? 'AES-256' : 'AES-128';
      var authAlgo = algo === 'SHA' ? 'SHA' : 'SHA-256';
      var body = {
        name: name, protocol: protocol, username: username,
        auth_key: auth, priv_key: priv,
        auth_algorithm: authAlgo, priv_algorithm: privAlgo,
        external_secret_ref: document.getElementById('c-secret-ref').value.trim() || '',
      };
    } else {
      var pass = document.getElementById('c-password').value;
      if (!pass) return showError(formError, 'SSH 需要密码或私钥');
      body = {
        name: name, protocol: protocol, username: username,
        auth_key: pass, auth_algorithm: 'SHA-256', priv_algorithm: 'AES-128',
        external_secret_ref: document.getElementById('c-secret-ref').value.trim() || '',
      };
    }
    var button = document.getElementById('btn-save-cred');
    button.disabled = true;
    document.getElementById('cred-spin').classList.remove('d-none');
    try {
      await api.post('/api/devices/credentials', body);
      resetCredForm();
      await loadCredentials();
      renderCredentials();
    } catch (err) {
      showError(formError, '保存凭据失败：' + err.message);
    } finally {
      button.disabled = false;
      document.getElementById('cred-spin').classList.add('d-none');
    }
  }
  async function triggerCollect(ids) {
    if (!ids || !ids.length) return;
    var button = document.querySelector('[data-collecting]');
    try {
      var resp = await api.post('/api/devices/collect', { device_ids: ids });
      var msg = resp && resp.status ? '设备 ' + ids.join(',') + ' 采集状态：' + (resp.error ? resp.error : resp.status) : '采集完成';
      alert(msg);
      loadDevices();
    } catch (err) {
      showError(listError, '采集失败：' + err.message);
    }
  }
  async function showInterfaces(deviceId, name) {
    hideError(document.getElementById('if-error'));
    document.getElementById('ifModalLabel').textContent = '接口指标：' + name;
    document.getElementById('if-tbody').innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">加载中...</td></tr>';
    ifModal.show();
    try {
      var data = await api.get('/api/devices/' + deviceId + '/interfaces?limit=50');
      var items = data || [];
      if (!items.length) {
        document.getElementById('if-tbody').innerHTML = '<tr><td colspan="7" class="empty-state"><i class="bi bi-activity"></i><div>暂无接口指标（未采集或采集失败）</div></td></tr>';
        return;
      }
      document.getElementById('if-tbody').innerHTML = items.map(function (m) {
        var status = m.status === 'ok' ? 'status-success' : (m.status === 'down' ? 'status-danger' : 'status-disabled');
        return '<tr>' +
          '<td>' + escapeHtml(m.interface_name) + '</td>' +
          '<td><span class="status-badge ' + status + '">' + (m.status || 'unknown') + '</span></td>' +
          '<td>' + (m.if_in_octets == null ? '<span class="text-muted">unknown</span>' : m.if_in_octets) + '</td>' +
          '<td>' + (m.if_out_octets == null ? '<span class="text-muted">unknown</span>' : m.if_out_octets) + '</td>' +
          '<td>' + rateText(m.in_rate_bps) + '</td>' +
          '<td>' + rateText(m.out_rate_bps) + '</td>' +
          '<td class="text-nowrap">' + fmtTime(m.collected_at) + '</td></tr>';
      }).join('');
    } catch (err) {
      showError(document.getElementById('if-error'), '加载接口指标失败：' + err.message);
    }
  }

  // ---- N2 配置备份与差异 ----
  async function showConfigs(deviceId, deviceName) {
    document.getElementById('cfg-device-name').textContent = deviceName;
    hideError(document.getElementById('cfg-error'));
    document.getElementById('cfg-tbody').innerHTML = '<tr><td colspan="5" class="text-center text-muted py-2">加载中…</td></tr>';
    document.getElementById('cfg-diff').textContent = '';
    document.getElementById('cfg-diff-meta').textContent = '';
    document.getElementById('cfg-latest').textContent = '';
    new bootstrap.Modal(document.getElementById('cfgModal')).show();
    try {
      var snaps = await api.get('/api/devices/' + deviceId + '/configs?page_size=50');
      var items = snaps.items || [];
      renderConfigSnapshots(items, deviceId);
      // 显示最新配置
      if (items.length) {
        var latest = await api.get('/api/devices/' + deviceId + '/configs/latest');
        document.getElementById('cfg-latest').textContent = latest.config_text_redacted || '(空)';
        // 自动对比最新两份
        if (items.length >= 2) {
          var diff = await api.get('/api/devices/' + deviceId + '/configs/diff');
          renderConfigDiff(diff);
        }
      }
    } catch (err) {
      showError(document.getElementById('cfg-error'), '加载配置快照失败：' + err.message);
    }
    document.getElementById('cfg-collect-btn').onclick = function () { triggerConfigCollect(deviceId); };
  }

  function renderConfigSnapshots(items, deviceId) {
    if (!items.length) {
      document.getElementById('cfg-tbody').innerHTML =
        '<tr><td colspan="5" class="text-center text-muted py-2">暂无配置快照（点击"采集配置快照"生成第一份）</td></tr>';
      return;
    }
    document.getElementById('cfg-tbody').innerHTML = items.map(function (s) {
      return '<tr>' +
        '<td>' + s.id + '</td>' +
        '<td class="text-nowrap">' + fmtTime(s.collected_at) + '</td>' +
        '<td class="text-monospace small" title="' + escapeHtml(s.config_full_hash) + '">' +
          escapeHtml((s.config_full_hash || '').substring(0, 12)) + '…</td>' +
        '<td>' + escapeHtml(s.source) + (s.truncated ? ' <span class="badge bg-danger">超限截断</span>' : '') + '</td>' +
        '<td>' + (s.changed ? '<span class="badge bg-warning text-dark">已变更</span>'
          : '<span class="badge bg-secondary">基准</span>') + '</td>' +
        '</tr>';
    }).join('');
  }

  function renderConfigDiff(d) {
    var meta = document.getElementById('cfg-diff-meta');
    var el = document.getElementById('cfg-diff');
    if (!d) { meta.textContent = '无可对比数据'; el.textContent = ''; return; }
    meta.textContent = (d.from_collected_at ? fmtTime(d.from_collected_at) : d.from_snapshot_id) +
      ' → ' + (d.to_collected_at ? fmtTime(d.to_collected_at) : d.to_snapshot_id) +
      (d.changed ? '  变更' : '  相同') +
      (d.capped ? '  ⚠️结果已截断' : '');
    el.textContent = d.text || '(无差异)';
    // 给 diff 行着色
    el.innerHTML = (d.text || '').split('\n').map(function (line) {
      if (line.startsWith('+')) return '<span class="text-success">' + escapeHtml(line) + '</span>';
      if (line.startsWith('-')) return '<span class="text-danger">' + escapeHtml(line) + '</span>';
      if (line.startsWith('~')) return '<span class="text-muted">' + escapeHtml(line) + '</span>';
      return escapeHtml(line);
    }).join('\n');
  }

  async function triggerConfigCollect(deviceId) {
    var errEl = document.getElementById('cfg-error');
    hideError(errEl);
    var btn = document.getElementById('cfg-collect-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>采集中…';
    try {
      var res = await api.post('/api/devices/' + deviceId + '/configs/collect', {});
      if (res.status === 'ok') {
        showConfigs(deviceId, document.getElementById('cfg-device-name').textContent);
      } else if (res.status === 'unchanged') {
        alert('配置内容未变化（hash 相同，未产生新快照）');
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-cloud-download me-1"></i>采集配置快照';
      } else {
        showError(errEl, '采集失败：' + (res.error || res.status));
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-cloud-download me-1"></i>采集配置快照';
      }
    } catch (err) {
      showError(errEl, '采集请求失败：' + err.message);
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-cloud-download me-1"></i>采集配置快照';
    }
  }

  // ---- 事件绑定 ----
  document.getElementById('filter-form').addEventListener('submit', function (event) {
    event.preventDefault();
    state.page = 1;
    loadDevices();
  });
  document.getElementById('btn-prev').addEventListener('click', function () {
    if (state.page > 1) { state.page -= 1; loadDevices(); }
  });
  document.getElementById('btn-next').addEventListener('click', function () {
    state.page += 1; loadDevices();
  });
  document.getElementById('btn-create').addEventListener('click', function () {
    openDeviceModal(null);
  });
  document.getElementById('btn-credential').addEventListener('click', function () {
    openCredModal();
  });
  document.getElementById('btn-collect-all').addEventListener('click', function () {
    var checked = Array.prototype.slice.call(document.querySelectorAll('.js-check:checked')).map(function (input) { return Number(input.dataset.id); });
    if (!checked.length) return alert('请先勾选要采集的设备');
    triggerCollect(checked);
  });
  document.getElementById('check-all').addEventListener('change', function (event) {
    Array.prototype.slice.call(document.querySelectorAll('.js-check')).forEach(function (input) { input.checked = event.target.checked; });
  });
  document.getElementById('device-form').addEventListener('submit', async function (event) {
    event.preventDefault();
    var formError = document.getElementById('form-error');
    hideError(formError);
    var name = document.getElementById('m-name').value.trim();
    var ip = document.getElementById('m-ip').value.trim();
    if (!name) return showError(formError, '请填写设备名称');
    if (!ip) return showError(formError, '请填写管理 IP');
    var body = {
      name: name, management_ip: ip,
      vendor_platform: document.getElementById('m-vendor').value,
      snmp_config_id: document.getElementById('m-snmp-cred').value ? Number(document.getElementById('m-snmp-cred').value) : null,
      ssh_config_id: document.getElementById('m-ssh-cred').value ? Number(document.getElementById('m-ssh-cred').value) : null,
    };
    var id = document.getElementById('device-id').value;
    var button = document.getElementById('btn-save');
    button.disabled = true;
    document.getElementById('save-spin').classList.remove('d-none');
    try {
      if (id) await api.put('/api/devices/' + encodeURIComponent(id), body);
      else await api.post('/api/devices', body);
      deviceModal.hide();
      loadDevices();
    } catch (err) {
      showError(formError, '保存失败：' + err.message);
    } finally {
      button.disabled = false;
      document.getElementById('save-spin').classList.add('d-none');
    }
  });
  tbody.addEventListener('click', async function (event) {
    var target = event.target.closest('button');
    if (!target) return;
    var id = Number(target.dataset.id);
    if (target.classList.contains('js-collect')) {
      triggerCollect([id]);
    } else if (target.classList.contains('js-interfaces')) {
      showInterfaces(id, target.dataset.name || ('#' + id));
    } else if (target.classList.contains('js-config')) {
      showConfigs(id, target.dataset.name || ('#' + id));
    } else if (target.classList.contains('js-edit')) {
      var device = state.items.find(function (item) { return item.id === id; });
      if (device) openDeviceModal(device);
    } else if (target.classList.contains('js-delete')) {
      if (!confirm('确认删除设备 ' + id + '？（关联接口指标一并删除）')) return;
      try {
        await api.del('/api/devices/' + id);
        loadDevices();
      } catch (err) {
        showError(listError, '删除失败：' + err.message);
      }
    }
  });
  document.getElementById('c-protocol').addEventListener('change', function () {
    toggleCredFields(this.value);
  });
  document.getElementById('cred-form').addEventListener('submit', function (event) {
    event.preventDefault();
    saveCredential();
  });
  document.getElementById('cred-tbody').addEventListener('click', async function (event) {
    var button = event.target.closest('button.js-del-cred');
    if (!button) return;
    if (!confirm('确认删除该凭据？')) return;
    try {
      await api.del('/api/devices/credentials/' + button.dataset.id);
      await loadCredentials();
      renderCredentials();
    } catch (err) {
      showError(document.getElementById('cred-error'), '删除失败：' + err.message);
    }
  });
  // 打开凭据弹窗时预加载
  loadCredentials();
  loadDevices();
})();