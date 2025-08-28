import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "your_solon.settings")

app = Celery("your_solon")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
