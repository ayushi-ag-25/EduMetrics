from django.core.management.base import BaseCommand
from analysis_engine.weekly_metrics_calculator import run as run_metrics
from analysis_engine.flagging import run as run_flagging
from analysis_engine.pre_mid_term import run as run_pre_mid

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        self.stdout.write('Running weekly analysis...')
        run_metrics()
        run_flagging()
        run_pre_mid()
        self.stdout.write('Done.')