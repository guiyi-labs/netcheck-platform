"""实时推送中枢：WebSocket 连接管理与线程安全的广播。

- executor 是后台线程，向 hub.publish 只是往每个连接的 asyncio.Queue 里 put_nowait
  （线程安全、非阻塞），由各 WebSocket 端点在自身事件循环中取出发送；
- 断线：连接对象从 hub 移除；端点侧用心跳 + 发送异常判定断开。
"""
import json
import threading
from dataclasses import dataclass, field

import asyncio


@dataclass
class _Conn:
    websocket: object
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)


class RealtimeHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._conns: dict[object, _Conn] = {}

    def subscribe(self, websocket) -> _Conn:
        conn = _Conn(websocket=websocket)
        with self._lock:
            self._conns[websocket] = conn
        return conn

    def unsubscribe(self, websocket) -> None:
        with self._lock:
            self._conns.pop(websocket, None)

    @property
    def connection_count(self) -> int:
        with self._lock:
            return len(self._conns)

    def publish(self, event: dict) -> None:
        """向所有连接广播事件。可在任意线程调用。"""
        payload = json.dumps(event, ensure_ascii=False, default=str)
        with self._lock:
            conns = list(self._conns.values())
        for conn in conns:
            try:
                conn.queue.put_nowait(payload)
            except Exception:
                continue


hub = RealtimeHub()