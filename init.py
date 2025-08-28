"""
Make Celery app importable as your_solon.celery_app.
This lets 'celery -A your_solon worker -l info' find the app.
"""
from your_solon.celery import app as celery_app

__all__ = ("celery_app",)
