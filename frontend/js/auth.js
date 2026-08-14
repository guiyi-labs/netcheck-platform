/**
 * 公共鉴权与顶部导航
 * - requireAuth()：无 token 则跳转 login.html
 * - currentUser()：读取 localStorage 中的用户对象
 * - logout()：调用后端登出后清空本地态并跳 login.html
 * - renderNav(containerId)：渲染统一顶部导航栏，并绑定退出事件
 * 挂到 window.Auth
 */
(function (global) {
  'use strict';

  var TOKEN_KEY = 'netcheck_token';
  var USER_KEY = 'netcheck_user';

  function requireAuth() {
    var token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      location.href = 'login.html';
      return false;
    }
    return true;
  }

  function currentUser() {
    var raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function escapeHtml(s) {
    if (s === undefined || s === null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  async function logout() {
    try {
      await global.api.post('/api/auth/logout', {});
    } catch (e) {
      // 即使后端报错也继续清理本地态
    }
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    location.href = 'login.html';
  }

  function activeClass(page) {
    var path = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
    return path === page.toLowerCase() ? ' active' : '';
  }

  /**
   * 渲染统一顶部导航栏到指定容器
   * @param {string} containerId 容器元素 id
   */
  function renderNav(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    var user = currentUser() || {};
    var username = escapeHtml(user.username || '未登录');
    var role = escapeHtml(user.role || '');

    el.innerHTML =
      '<nav class="navbar navbar-expand-lg app-navbar">' +
        '<div class="container-fluid">' +
          '<a class="navbar-brand d-flex align-items-center" href="index.html">' +
            '<i class="bi bi-hdd-network nav-brand-icon"></i>' +
            '<span class="nav-brand-text">巡检诊断平台</span>' +
          '</a>' +
          '<button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#appNav" aria-controls="appNav" aria-expanded="false" aria-label="切换导航">' +
            '<span class="navbar-toggler-icon"></span>' +
          '</button>' +
          '<div class="collapse navbar-collapse" id="appNav">' +
            '<ul class="navbar-nav me-auto">' +
              '<li class="nav-item"><a class="nav-link' + activeClass('index.html') + '" href="index.html"><i class="bi bi-speedometer2 me-1"></i>仪表盘</a></li>' +
              '<li class="nav-item"><a class="nav-link' + activeClass('assets.html') + '" href="assets.html"><i class="bi bi-hdd-stack me-1"></i>资产管理</a></li>' +
              '<li class="nav-item"><a class="nav-link' + activeClass('discovery.html') + '" href="discovery.html"><i class="bi bi-radar me-1"></i>资产发现</a></li>' +
              '<li class="nav-item"><a class="nav-link' + activeClass('topology.html') + '" href="topology.html"><i class="bi bi-diagram-3 me-1"></i>逻辑拓扑</a></li>' +
              '<li class="nav-item"><a class="nav-link' + activeClass('tasks.html') + activeClass('task-run.html') + '" href="tasks.html"><i class="bi bi-clipboard2-pulse me-1"></i>巡检任务</a></li>' +
              '<li class="nav-item"><a class="nav-link' + activeClass('diag.html') + '" href="diag.html"><i class="bi bi-signpost-split me-1"></i>网络诊断</a></li>' +
              '<li class="nav-item"><a class="nav-link' + activeClass('results.html') + '" href="results.html"><i class="bi bi-clipboard-data me-1"></i>巡检结果</a></li>' +
              '<li class="nav-item"><a class="nav-link' + activeClass('trends.html') + '" href="trends.html"><i class="bi bi-graph-up me-1"></i>趋势分析</a></li>' +
              '<li class="nav-item"><a class="nav-link' + activeClass('diagnosis.html') + '" href="diagnosis.html"><i class="bi bi-tools me-1"></i>故障诊断</a></li>' +
              '<li class="nav-item"><a class="nav-link' + activeClass('alerts.html') + '" href="alerts.html"><i class="bi bi-bell me-1"></i>告警中心</a></li>' +
              '<li class="nav-item"><a class="nav-link' + activeClass('reports.html') + '" href="reports.html"><i class="bi bi-file-earmark-spreadsheet me-1"></i>报告管理</a></li>' +
              '<li class="nav-item"><a class="nav-link' + activeClass('audit.html') + '" href="audit.html"><i class="bi bi-journal-text me-1"></i>审计日志</a></li>' +
              (role === 'admin' ? '<li class="nav-item"><a class="nav-link' + activeClass('users.html') + '" href="users.html"><i class="bi bi-people me-1"></i>用户管理</a></li>' : '') +
            '</ul>' +
            '<ul class="navbar-nav align-items-center">' +
              '<li class="nav-item dropdown">' +
                '<a class="nav-link dropdown-toggle user-menu" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">' +
                  '<i class="bi bi-person-circle me-1"></i><span class="user-name">' + username + '</span>' +
                '</a>' +
                '<ul class="dropdown-menu dropdown-menu-end">' +
                  '<li class="px-3 py-1 small text-muted">角色：' + (role || '-') + '</li>' +
                  '<li><hr class="dropdown-divider"></li>' +
                  '<li><a class="dropdown-item" href="#" id="navLogout"><i class="bi bi-box-arrow-right me-1"></i>退出登录</a></li>' +
                '</ul>' +
              '</li>' +
            '</ul>' +
          '</div>' +
        '</div>' +
      '</nav>';

    var btn = el.querySelector('#navLogout');
    if (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        logout();
      });
    }
  }

  global.Auth = {
    requireAuth: requireAuth,
    currentUser: currentUser,
    logout: logout,
    renderNav: renderNav,
  };
})(window);
