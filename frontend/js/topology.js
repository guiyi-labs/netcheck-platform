(function () {
  'use strict';
  if (!Auth.requireAuth()) return;
  Auth.renderNav('app-nav');

  var chart = null;
  var chartEl = document.getElementById('topology-chart');
  var fallbackEl = document.getElementById('topology-fallback');
  var errorEl = document.getElementById('topology-error');
  var detailEl = document.getElementById('node-detail');
  var state = { nodes: [], links: [] };

  function escapeHtml(value) { return value == null ? '' : String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
  function hideError() { errorEl.textContent = ''; errorEl.classList.add('d-none'); }
  function showError(message) { errorEl.textContent = message; errorEl.classList.remove('d-none'); }
  function statusLabel(status) { return { online: '在线', offline: '离线', warning: '告警', unknown: '未知' }[status] || status || '-'; }
  function categoryLabel(category) { return category === 'core' ? '核心网络' : (category || '资产'); }
  function showFallback(message) { chartEl.classList.add('d-none'); fallbackEl.textContent = message; fallbackEl.classList.remove('d-none'); }
  function hideFallback() { chartEl.classList.remove('d-none'); fallbackEl.textContent = ''; fallbackEl.classList.add('d-none'); }
  function renderDetail(node) {
    if (!node) { detailEl.className = 'node-detail empty-state'; detailEl.innerHTML = '<i class="bi bi-cursor"></i><div>点击拓扑节点查看详情</div>'; return; }
    detailEl.className = 'node-detail';
    detailEl.innerHTML = '<div class="detail-title">' + escapeHtml(node.label || node.id) + '</div><dl class="row mb-0 small"><dt class="col-4">ID</dt><dd class="col-8">' + escapeHtml(node.id) + '</dd><dt class="col-4">类型</dt><dd class="col-8">' + escapeHtml(categoryLabel(node.category)) + '</dd><dt class="col-4">状态</dt><dd class="col-8"><span class="status-badge status-' + escapeHtml(node.status || 'unknown') + '">' + escapeHtml(statusLabel(node.status)) + '</span></dd></dl>';
  }
  function renderListFallback() {
    if (!state.nodes.length) { showFallback('暂无拓扑节点'); return; }
    chartEl.classList.add('d-none'); fallbackEl.classList.remove('d-none');
    fallbackEl.innerHTML = '<div class="w-100"><div class="mb-2">图表库加载失败，以下为节点列表：</div><div class="topology-node-list">' + state.nodes.map(function (node) { return '<button type="button" class="topology-node-item" data-id="' + escapeHtml(node.id) + '"><span class="legend-dot" style="background:' + escapeHtml(node.color || '#64748b') + '"></span>' + escapeHtml(node.label || node.id) + '<small>' + escapeHtml(statusLabel(node.status)) + '</small></button>'; }).join('') + '</div></div>';
  }
  function renderChart() {
    if (!state.nodes.length) { showFallback('暂无拓扑数据'); renderDetail(null); return; }
    if (!window.echarts) { renderListFallback(); return; }
    hideFallback();
    if (chart) chart.dispose();
    chart = echarts.init(chartEl);
    chart.setOption({
      tooltip: { formatter: function (p) { if (p.dataType !== 'node') return ''; return escapeHtml(p.data.label || p.data.id) + '<br/>类型：' + escapeHtml(categoryLabel(p.data.category)) + '<br/>状态：' + escapeHtml(statusLabel(p.data.status)); } },
      series: [{
        type: 'graph', layout: 'force', roam: true, draggable: true, focusNodeAdjacency: true,
        force: { repulsion: 220, edgeLength: 120 }, symbolSize: function (value, params) { return params.data.category === 'core' ? 64 : 42; },
        label: { show: true, position: 'bottom', formatter: '{b}' }, edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 8,
        lineStyle: { color: '#94a3b8', width: 1.4, curveness: 0.05 },
        categories: [{ name: 'core' }, { name: 'asset' }],
        data: state.nodes.map(function (node) { return { id: node.id, name: node.label || node.id, label: node.label, category: node.category, status: node.status, itemStyle: { color: node.color || '#64748b' } }; }),
        links: state.links.map(function (link) { return { source: link.source, target: link.target }; })
      }]
    });
    chart.on('click', function (params) { if (params.dataType === 'node') renderDetail(params.data); });
  }
  async function loadTopology() {
    hideError(); renderDetail(null); showFallback('拓扑数据加载中...');
    try { var data = await api.get('/api/topology'); state.nodes = data && data.nodes || []; state.links = data && data.links || []; renderChart(); }
    catch (err) { state.nodes = []; state.links = []; showFallback('拓扑加载失败'); showError('加载逻辑拓扑失败：' + err.message); }
  }
  fallbackEl.addEventListener('click', function (event) { var btn = event.target.closest('.topology-node-item'); if (!btn) return; var id = btn.getAttribute('data-id'); var node = state.nodes.filter(function (item) { return String(item.id) === id; })[0]; renderDetail(node); });
  document.getElementById('btn-refresh-topology').addEventListener('click', loadTopology);
  window.addEventListener('resize', function () { if (chart) chart.resize(); });
  loadTopology();
})();
