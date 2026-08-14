"""告警通知分发（B 阶段完善）。

当前为占位实现：仅提供 dispatch_alert_notifications 函数的空版本，
使巡检执行主流程可以调用而无需感知通知是否启用。
"""
import logging

logger = logging.getLogger("netcheck.notifications")


def dispatch_alert_notifications(run_id: int, db) -> None:
    """分发一次巡检运行产生的告警通知。

    在 B1（邮件/Webhook）实现前作为空操作；执行循环已捕获异常，
    因此即使实现尚未完成也不影响巡检主流程。
    """
    return None