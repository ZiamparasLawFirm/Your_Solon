# -*- coding: utf-8 -*-
from __future__ import annotations
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from .models import CivilSearchJob, Case, CaseSnapshot
from .solon_scraper_adf import scrape_solon_civil_adf

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=20, retry_kwargs={"max_retries": 2})
def run_solon_lookup(self, job_id: int):
    job = CivilSearchJob.objects.select_related("court").get(id=job_id)
    job.status = "running"
    job.save(update_fields=["status"])

    try:
        data = scrape_solon_civil_adf(job.court.name, job.gak_number, job.gak_year)
        fields = data.get("fields") or {}

        with transaction.atomic():
            case, _ = Case.objects.get_or_create(
                court=job.court,
                gak_number=job.gak_number,
                gak_year=job.gak_year,
                defaults={"client_name": job.client_name},
            )
            snapshot = CaseSnapshot.objects.create(
                case=case,
                details=fields,
                raw=data,
                created_at=timezone.now(),
            )
            job.case = case
            job.snapshot = snapshot
            job.status = "done"
            job.error_message = ""
            job.save(update_fields=["case", "snapshot", "status", "error_message"])
        return True

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.save(update_fields=["status", "error_message"])
        raise
