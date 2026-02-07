import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'judge_vortex.settings')
app = Celery('judge_vortex')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()