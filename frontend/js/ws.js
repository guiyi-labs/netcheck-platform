/**
 * 实时推送客户端
 * - 基于登录 token 建立 /ws/runs 连接，服务端推送巡检运行状态事件
 * - 提供 Realtime.on(type, handler) 订阅；断线自动指数退避重连
 * - 兼容任意事件类型，payload 为 {type, run_id, task_id, status, ...}
 */
(function (global) {
  'use strict';

  var TOKEN_KEY = 'netcheck_token';
  var handlers = {};
  var ws = null;
  var reconnectDelay = 1000;
  var closedByUser = false;

  function connect() {
    var token = localStorage.getItem(TOKEN_KEY) || '';
    if (!token || closedByUser) return;
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var url = proto + '//' + location.host + '/ws/runs?token=' + encodeURIComponent(token);
    try {
      ws = new WebSocket(url);
    } catch (e) { return; }
    ws.onopen = function () { reconnectDelay = 1000; };
    ws.onmessage = function (event) {
      var msg = null;
      try { msg = JSON.parse(event.data); } catch (e) { return; }
      if (!msg || typeof msg !== 'object' || msg.type === 'ping') return;
      if (handlers[msg.type]) {
        handlers[msg.type].slice().forEach(function (fn) { try { fn(msg); } catch (e) {} });
      }
      if (handlers['*']) {
        handlers['*'].slice().forEach(function (fn) { try { fn(msg); } catch (e) {} });
      }
    };
    ws.onclose = function () {
      ws = null;
      if (closedByUser) return;
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 15000);
    };
    ws.onerror = function () { try { ws.close(); } catch (e) {} };
  }

  var Realtime = {
    connect: connect,
    on: function (type, fn) {
      (handlers[type] = handlers[type] || []).push(fn);
      return function () {
        var arr = handlers[type];
        if (arr) { var i = arr.indexOf(fn); if (i >= 0) arr.splice(i, 1); }
      };
    },
    isConnected: function () { return ws !== null && ws.readyState === WebSocket.OPEN; },
    disconnect: function () { closedByUser = true; try { if (ws) ws.close(); } catch (e) {} },
  };

  global.Realtime = Realtime;
})(window);