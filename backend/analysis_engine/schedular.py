from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management import call_command

def run_weekly():
    call_command('run_weekly')

def start():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_weekly,
        CronTrigger(day_of_week='sat', hour=23, minute=50),
        id='weekly_analysis',
        replace_existing=True,
    )
    scheduler.start()