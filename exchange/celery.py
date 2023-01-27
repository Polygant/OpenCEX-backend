from .celery_app import app


app.autodiscover_tasks()
