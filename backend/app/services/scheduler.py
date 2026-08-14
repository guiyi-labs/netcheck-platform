from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import selectinload

from app.core.database import SessionLocal
from app.models.inspection import InspectionTask


class SchedulerService:
    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def reload_all(self) -> None:
        for job in self.scheduler.get_jobs():
            if job.id.startswith("inspection-task-"):
                job.remove()
        db = SessionLocal()
        try:
            task_ids = [row[0] for row in db.query(InspectionTask.id).all()]
        finally:
            db.close()
        for task_id in task_ids:
            self.reload_task(task_id)

    def reload_task(self, task_id: int) -> None:
        job_id = self._job_id(task_id)
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        db = SessionLocal()
        try:
            task = db.get(InspectionTask, task_id)
            if task is None or not task.enabled or not task.schedule_enabled or not self._schedule_interval(task):
                return
            self.scheduler.add_job(
                self.scheduled_run_task,
                trigger=IntervalTrigger(minutes=task.schedule_interval_minutes),
                args=[task_id],
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        finally:
            db.close()

    def get_status(self) -> dict:
        return {
            "running": self.scheduler.running,
            "jobs": [
                {
                    "id": job.id,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                }
                for job in self.scheduler.get_jobs()
            ],
        }

    def scheduled_run_task(self, task_id: int) -> None:
        from app.services.executor import enqueue_task_run

        db = SessionLocal()
        try:
            task = (
                db.query(InspectionTask)
                .options(selectinload(InspectionTask.assets))
                .filter(InspectionTask.id == task_id)
                .first()
            )
            if task is None or not task.enabled:
                return
            enqueue_task_run(task_id, trigger_type="scheduled")
        finally:
            db.close()

    @staticmethod
    def _schedule_interval(task: InspectionTask) -> int | None:
        return task.schedule_interval_minutes

    @staticmethod
    def _job_id(task_id: int) -> str:
        return f"inspection-task-{task_id}"


scheduler_service = SchedulerService()