"""定时调度辅助：Cron 表达式解析与下次执行时间计算。

独立于 inspection/executor/scheduler，避免循环导入。
"""
from datetime import datetime, timedelta

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

SCHEDULER_TZ = "Asia/Shanghai"


def cron_trigger(expression: str) -> CronTrigger:
    return CronTrigger.from_crontab(expression, timezone=SCHEDULER_TZ)


def interval_trigger(minutes: int) -> IntervalTrigger:
    return IntervalTrigger(minutes=minutes)


def validate_cron(expression: str) -> None:
    cron_trigger(expression)


def next_run_at(schedule_enabled: bool, schedule_cron: str | None, schedule_interval_minutes: int | None) -> datetime | None:
    """根据调度配置计算下次执行时间；未启用调度或未配置任何触发器时返回 None。"""
    if not schedule_enabled:
        return None
    if schedule_cron:
        try:
            return cron_trigger(schedule_cron).get_next_fire_time(None, datetime.now())
        except Exception:
            return None
    if not schedule_interval_minutes:
        return None
    return datetime.now() + timedelta(minutes=schedule_interval_minutes)