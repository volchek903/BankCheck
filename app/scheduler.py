from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.bot import FinanceBotApp


def create_scheduler(app: FinanceBotApp) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=app.timezone)
    for hour in app.settings.schedule_hours:
        scheduler.add_job(
            app.send_scheduled_reports,
            trigger=CronTrigger(hour=hour, minute=0, timezone=app.timezone),
            id=f"daily-report-{hour}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    return scheduler
