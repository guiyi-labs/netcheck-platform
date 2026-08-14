"""WebSocket 实时端点：/ws/runs?token=...

- 客户端用登录 token 建立连接后，服务端推送巡检运行状态事件：
  {"type": "run.updated", "run_id": ..., "task_id": ..., "status": ...}
- 连接空闲 30 秒发送心跳文本（ping），浏览器 WebSocket 会自动回应，用于探测断线。
"""
import asyncio
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import utcnow
from app.models.user import User
from app.services.realtime import hub

router = APIRouter(tags=["realtime"])

HEARTBEAT_INTERVAL = 30.0


def _validate_token(token: str) -> bool:
    """校验 WS token：与登录 token 同源（api_token 字段 + 有效期 + 启用）。"""
    if not token:
        return False
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.api_token == token).first()
        if user is None or not user.is_active:
            return False
        if user.api_token_expires_at is not None:
            return user.api_token_expires_at > utcnow()
        return True
    finally:
        db.close()


@router.websocket("/ws/runs")
async def ws_runs(websocket: WebSocket, token: str = Query("")) -> None:
    if not _validate_token(token):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    conn = hub.subscribe(websocket)
    try:
        while True:
            try:
                payload = await asyncio.wait_for(conn.queue.get(), timeout=HEARTBEAT_INTERVAL)
            except asyncio.TimeoutError:
                # 空闲心跳：检测连接是否仍然存活
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue
            await websocket.send_text(payload)
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        pass
    finally:
        hub.unsubscribe(websocket)