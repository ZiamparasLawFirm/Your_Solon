"""
Celery app bootstrap for 'your_solon'.

- Loads settings from Django using the CELERY_ namespace.
- Auto-discovers tasks.py inside installed apps (e.g., civil_app.tasks).
"""

import os
from celery import Celery

# Ensure Django settings are loaded
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "your_solon.settings")

# Create Celery app and load config from Django settings
app = Celery("your_solon")
app.config_from_object("django.conf:settings", namespace="CELERY")

# Discover tasks in installed apps
app.autodiscover_tasks()
