import logging
import traceback
from typing import Optional

from django.db import transaction

from .models import Court, Case, CaseSnapshot, CivilSearchJob
from .solon_scraper_adf import scrape_solon_civil_adf
from .normalizers import clean_solon_fields

logger = logging.getLogger(__name__)


def _get_court_obj(job) -> Optional[Court]:
    """
    Return a Court instance for this job, if resolvable.
    """
    try:
        v = getattr(job, "court", None)
        # If it's already a relation
        if v and isinstance(v, Court):
            return v
    except Exception:
        pass

    # Try FK id
    try:
        cid = getattr(job, "court_id", None)
        if cid:
            return Court.objects.get(id=int(cid))
    except Exception:
        logger.exception("Could not resolve Court for job id=%s", getattr(job, "id", None))
    return None


def _get_court_label(job) -> str:
    """
    A human-friendly label to pass to the scraper (Court.name if available).
    """
    c = _get_court_obj(job)
    return (c.name if c and getattr(c, "name", None) else "") or ""


def _ensure_job_case(job) -> Case:
    """
    Ensure job.case exists.
    We key Cases primarily by (court, gak_number, gak_year) when possible.
    Fallback to (court, subject) or plain subject.
    """
    if getattr(job, "case_id", None):
        return job.case

    court = _get_court_obj(job)
    gak_number = (str(getattr(job, "gak_number", "")).strip() or None)
    try:
        gak_year = int(getattr(job, "gak_year", 0)) or None
    except Exception:
        gak_year = None

    # Prefer a readable subject if present on the job
    subject = (getattr(job, "subject", "") or "").strip() or "Χωρίς τίτλο"

    # Build a robust get_or_create filter set
    qs_filter = {}
    if court:
        qs_filter["court"] = court
    if gak_number:
        qs_filter["gak_number"] = gak_number
    if gak_year:
        qs_filter["gak_year"] = gak_year

    if qs_filter:
        # Use the strongest identity we have; set subject as a default if creating
        case, _ = Case.objects.get_or_create(
            **qs_filter,
            defaults={
                "subject": subject,
                # Populate optional metadata if your model has them:
                "procedure": getattr(job, "procedure", "") or "",
                "pleading_type": getattr(job, "pleading_type", "") or "",
                "eak_number": getattr(job, "eak_number", "") or "",
                "eak_year": getattr(job, "eak_year", "") or None,
            },
        )
    else:
        # Absolute fallback: only subject
        case, _ = Case.objects.get_or_create(
            subject=subject,
            defaults={
                "court": court,
                "gak_number": gak_number or "",
                "gak_year": gak_year or 0,
                "procedure": getattr(job, "procedure", "") or "",
                "pleading_type": getattr(job, "pleading_type", "") or "",
                "eak_number": getattr(job, "eak_number", "") or "",
                "eak_year": getattr(job, "eak_year", "") or None,
            },
        )

    job.case = case
    try:
        job.save(update_fields=["case"])
    except Exception:
        job.save()
    return case


def _has_meaningful_values(d: dict) -> bool:
    """
    Treat non-empty strings/numbers as meaningful. Empty/None/whitespace is not.
    """
    if not isinstance(d, dict) or not d:
        return False
    for v in d.values():
        if isinstance(v, str) and v.strip():
            return True
        if isinstance(v, (int, float)) and v:
            return True
    return False


def _run_job(job_id: int) -> None:
    job = CivilSearchJob.objects.select_for_update(of=("self",)).get(id=job_id)

    # Mark running
    job.status = "running"
    job.error = ""
    job.save(update_fields=["status", "error"])

    try:
        court_label = _get_court_label(job)
        gak_num = str(getattr(job, "gak_number", "")).strip()
        gak_year = int(getattr(job, "gak_year", 0))

        # Scrape
        raw = scrape_solon_civil_adf(court_label, gak_num, gak_year)

        # Normalize to displayable dict (Greek keys, etc.)
        fields = clean_solon_fields(raw)

        # Persist snapshot atomically, ensuring we have a Case
        with transaction.atomic():
            case = _ensure_job_case(job)
            snap = CaseSnapshot.objects.create(case=case, data_json=fields)
            job.snapshot = snap

            job.status = "done" if _has_meaningful_values(fields) else "no_results"
            job.save(update_fields=["snapshot", "status"])

    except Exception as e:
        tb = traceback.format_exc()
        logger.error("Job %s failed: %s\n%s", job_id, e, tb)
        job.status = "error"
        job.error = f"{e}\n{tb}"
        try:
            job.save(update_fields=["status", "error"])
        except Exception:
            job.save()


def start_civil_job(job_id: int) -> None:
    """
    Placeholder for async queue. Currently runs synchronously.
    """
    run_civil_job(job_id)


def run_civil_job(job_id: int) -> None:
    """
    Entry point invoked by views.
    """
    _run_job(job_id)
