(function () {
  'use strict';
  if (!Auth.requireAuth()) return;
  Auth.renderNav('app-nav');
  var errorBox = document.getElementById('page-error');
  function escapeHtml(v) { return v == null ? '' : String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function showError(msg) { errorBox.textContent = msg; errorBox.classList.remove('d-none'); } function hideError() { errorBox.classList.add('d-none'); errorBox.textContent = ''; }
  function statusClass(s) { return s === 'completed' ? 'status-success' : s === 'timeout' ? 'status-warning' : 'status-failed'; }
  function statusLabel(s) { return { completed: '已到达', timeout: '超时未达', failed: '失败' }[s] || s; }
  function fmtRtt(r) { return r == null ? '<span class="text-muted">超时</span>' : escapeHtml(r) + ' ms'; }
  function render(data) {
    var content = document.getElementById('result-content');
    var placeholder = document.getElementById('result-placeholder');
    var summary = document.getElementById('result-summary');
    placeholder.classList.add('d-none'); content.classList.remove('d-none');
    summary.innerHTML = '<i class="bi bi-info-circle me-1"></i>目标 <b>' + escapeHtml(data.target) + '</b>：<span class="status-badge ' + statusClass(data.status) + '">' + statusLabel(data.status) + '</span>' + (data.elapsed_ms != null ? '（用时 ' + escapeHtml(data.elapsed_ms) + ' ms）' : '') + (data.error ? '<div class="mt-1">' + escapeHtml(data.error) + '</div>' : '');
    var tbody = document.getElementById('hops-tbody');
    tbody.innerHTML = data.hops && data.hops.length ? data.hops.map(function (hop) {
      var host = hop.host && hop.host !== hop.ip ? escapeHtml(hop.host) + ' ' : '';
      var ip = hop.ip ? '<span class="text-muted">(' + escapeHtml(hop.ip) + ')</span>' : '';
      var rtts = (hop.rtts && hop.rtts.length ? hop.rtts : [null]).map(fmtRtt).join('</td><td>');
      return '<tr><td>' + escapeHtml(hop.hop) + '</td><td>' + host + '</td><td class="text-nowrap">' + ip + '</td><td>' + rtts + '</td></tr>';
    }).join('') : '<tr><td colspan="6" class="empty-state"><i class="bi bi-signpost-split"></i><div>没有探测到任何跳点</div></td></tr>';
  }
  document.getElementById('btn-run').addEventListener('click', async function () {
    var target = document.getElementById('diag-target').value.trim();
    if (!target) { showError('请输入目标 IP 或主机名'); return; }
    hideError();
    var btn = document.getElementById('btn-run'); btn.disabled = true;
    document.getElementById('run-spin').classList.remove('d-none');
    try {
      var hops = Number(document.getElementById('diag-hops').value) || 15;
      var data = await api.post('/api/diagnostics/traceroute?target=' + encodeURIComponent(target) + '&max_hops=' + hops, {});
      render(data);
    } catch (err) { showError('诊断失败：' + err.message); }
    finally { btn.disabled = false; document.getElementById('run-spin').classList.add('d-none'); }
  });
  document.getElementById('diag-target').addEventListener('keydown', function (e) { if (e.key === 'Enter') document.getElementById('btn-run').click(); });
})();