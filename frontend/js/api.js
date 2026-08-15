/**
 * 公共 API 请求封装
 * - 自动附加 Authorization: Bearer {token}
 * - 解析统一响应包络 {code, message, data}，code!==0 抛错并抛出后端 message
 * - 401 且本地已有 token：清空本地态并跳转 login.html
 *   （登录接口本身无 token，不会触发跳转，仍会抛出后端错误信息）
 * - 挂到 window.api，提供 get / post / put / del 方法
 */
(function (global) {
  'use strict';

  var TOKEN_KEY = 'netcheck_token';
  var USER_KEY = 'netcheck_user';

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || '';
  }

  function clearAuth() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  function redirectToLogin() {
    // 避免在 login.html 上反复跳转
    var current = (location.pathname.split('/').pop() || '').toLowerCase();
    if (current !== 'login.html') {
      location.href = 'login.html';
    }
  }

  /**
   * 发起请求并解析统一包络
   * @param {string} method HTTP 方法
   * @param {string} url 请求地址
   * @param {*} body 请求体，传 undefined/null 表示无 body
   * @returns {Promise<any>} 包络中的 data 字段
   */
  async function request(method, url, body) {
    var opts = { method: method, headers: {} };
    var token = getToken();
    var hadToken = !!token;
    if (token) {
      opts.headers['Authorization'] = 'Bearer ' + token;
    }
    if (body !== undefined && body !== null) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }

    var resp;
    try {
      resp = await fetch(url, opts);
    } catch (e) {
      throw new Error('网络请求失败：' + (e && e.message ? e.message : e));
    }

    // 已登录但 token 失效或权限不足：清理并跳登录
    if (resp.status === 401 && hadToken) {
      clearAuth();
      redirectToLogin();
      throw new Error('登录已失效，请重新登录');
    }

    var payload = null;
    var text = '';
    try {
      text = await resp.text();
    } catch (e) {
      text = '';
    }
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (e) {
        throw new Error('响应解析失败');
      }
    }

    // 统一包络 {code, message, data}
    if (payload && typeof payload === 'object' && 'code' in payload) {
      if (payload.code !== 0) {
        // 未登录请求（如登录凭据错误）也走这里，抛出后端 message
        throw new Error(payload.message || ('请求失败 code=' + payload.code));
      }
      return payload.data;
    }

    // 非包络响应
    if (!resp.ok) {
      throw new Error('请求失败 HTTP ' + resp.status);
    }
    return payload;
  }

  var api = {
    request: request,
    get: function (url) { return request('GET', url, null); },
    post: function (url, body) { return request('POST', url, body); },
    put: function (url, body) { return request('PUT', url, body); },
    del: function (url) { return request('DELETE', url, null); },
    // 下载（blob + Content-Disposition；失败 reject）
    download: function (url) {
      return fetch(url, { headers: { 'Authorization': 'Bearer ' + getToken() } })
        .then(function (resp) {
          if (!resp.ok) throw new Error('下载失败 HTTP ' + resp.status);
          return resp.blob();
        })
        .then(function (blob) {
          var disposition = '';
          var urlObj = new URL(url, window.location.origin);
          var name = (urlObj.pathname.split('/').pop() || 'download') + '.bin';
          var link = document.createElement('a');
          link.href = URL.createObjectURL(blob);
          link.download = name;
          document.body.appendChild(link);
          link.click();
          URL.revokeObjectURL(link.href);
          link.remove();
          return true;
        });
    },
  };

  global.api = api;
})(window);
