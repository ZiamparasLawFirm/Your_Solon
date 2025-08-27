"""
Celery task that automates the SOLON Track page to fetch Civil case details.

Flow:
1) Open page https://extapps.solon.gov.gr/mojwp/faces/TrackLdoPublic
2) Select Κατάστημα, fill ΓΑΚ Αριθμός and Έτος
3) Click Αναζήτηση, wait for results to appear
4) Extract key fields; upsert Case; create CaseSnapshot
5) Update CivilSearchJob status to done (or failed on error)

Includes a 6-hour cache: if a recent snapshot exists, we reuse it without scraping.
"""

import random
import time
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from .models import CivilSearchJob, Case, CaseSnapshot

SOLON_TRACK_URL = "https://extapps.solon.gov.gr/mojwp/faces/TrackLdoPublic"

def _human_sleep(a: float = 0.6, b: float = 1.4) -> None:
    """Sleep a random human-like amount between a and b seconds."""
    time.sleep(random.uniform(a, b))

@shared_task(bind=True, max_retries=2, default_retry_delay=20)
def run_solon_lookup(self, job_id: int) -> None:
    """Celery task to perform the SOLON civil case lookup for a given CivilSearchJob."""
    job = CivilSearchJob.objects.select_related("court").get(pk=job_id)

    # Only handle queued/failed jobs
    if job.status not in ("queued", "failed"):
        return

    # Flip to running
    job.status = "running"
    job.save(update_fields=["status", "updated_at"])

    # Try to reuse fresh snapshot if available (6 hours)
    six_hours_ago = timezone.now() - timezone.timedelta(hours=6)
    preexisting_case = Case.objects.filter(
        court=job.court, gak_number=job.gak_number, gak_year=job.gak_year
    ).first()
    if preexisting_case:
        recent = preexisting_case.snapshots.filter(scraped_at__gte=six_hours_ago).order_by("-scraped_at").first()
        if recent:
            job.status = "done"
            job.case = preexisting_case
            job.snapshot = recent
            job.save(update_fields=["status", "case", "snapshot", "updated_at"])
            return

    # Otherwise perform a fresh scrape
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = browser.new_context(locale="el-GR")
            page = ctx.new_page()
            page.goto(SOLON_TRACK_URL, wait_until="domcontentloaded", timeout=45000)

            # Select Κατάστημα (court)
            try:
                select_el = page.get_by_label("Κατάστημα", exact=False)
                if select_el.count():
                    select_el.select_option(label=job.court.name)
                else:
                    # Fallback to first <select> if label match fails
                    page.locator("select").first.select_option(label=job.court.name)
            except Exception:
                # Last-resort: click and type the visible text
                page.locator("select").first.click()
                page.keyboard.type(job.court.name)
            _human_sleep()

            # Fill ΓΑΚ and Έτος
            page.get_by_label("ΓΑΚ Αριθμός", exact=False).fill(job.gak_number)
            _human_sleep()
            page.get_by_label("Έτος", exact=False).fill(str(job.gak_year))
            _human_sleep()

            # Click Αναζήτηση and allow results to load
            page.get_by_role("button", name="Αναζήτηση", exact=False).click()
            page.wait_for_timeout(2300)  # simple wait; tune with explicit waits if needed

            # Read helper: try a set of candidate Greek labels and return following node's text
            def try_read(label_candidates: list[str]) -> str:
                for lbl in label_candidates:
                    try:
                        el = page.get_by_text(lbl, exact=False).locator("xpath=following::*[1]")
                        txt = el.inner_text().strip()
                        if txt:
                            return txt
                    except Exception:
                        pass
                return ""

            # Extract data payload (expand as you discover more stable fields)
            data = {
                "Κατάστημα": job.court.name,
                "ΓΑΚ": f"{job.gak_number}/{job.gak_year}",
                "Διαδικασία": try_read(["Διαδικασία"]),
                "Αντικείμενο": try_read(["Αντικείμενο"]),
                "Είδος Δικογράφου": try_read(["Είδος Δικογράφου"]),
                "EAK": try_read(["Ειδικός Αριθμός Κατάθεσης", "E.A.K.", "Ε.Α.Κ."]),
                "EAK Έτος": try_read(["E.A.K. Έτος", "Ε.Α.Κ. Έτος", "Έτος EAK"]),
            }

            # Upsert Case + create Snapshot atomically
            with transaction.atomic():
                case, _created = Case.objects.select_for_update().get_or_create(
                    court=job.court,
                    gak_number=job.gak_number,
                    gak_year=job.gak_year,
                    defaults=dict(
                        procedure=data.get("Διαδικασία", ""),
                        subject=data.get("Αντικείμενο", ""),
                        pleading_type=data.get("Είδος Δικογράφου", ""),
                        eak_number=(data.get("EAK") or "").strip(),
                        eak_year=int(data.get("EAK Έτος")) if (data.get("EAK Έτος") or "").isdigit() else None,
                    ),
                )

                # Opportunistically update a few fields if values improved
                changed = False
                for model_field, key in [
                    ("procedure", "Διαδικασία"),
                    ("subject", "Αντικείμενο"),
                    ("pleading_type", "Είδος Δικογράφου"),
                ]:
                    new_val = data.get(key, "") or ""
                    if new_val and getattr(case, model_field) != new_val:
                        setattr(case, model_field, new_val)
                        changed = True
                if changed:
                    case.save(update_fields=["procedure", "subject", "pleading_type", "updated_at"])

                snap = CaseSnapshot.objects.create(
                    case=case, data_json=data, scraper_version="v1", created_by_username="system"
                )

                # Mark job as completed
                job.status = "done"
                job.case = case
                job.snapshot = snap
                job.save(update_fields=["status", "case", "snapshot", "updated_at"])

            ctx.close()
            browser.close()

    except PWTimeout as e:
        # Retry transient timeouts
        job.status = "failed"
        job.error_text = f"Timeout: {e}"
        job.save(update_fields=["status", "error_text", "updated_at"])
        raise self.retry(exc=e)

    except Exception as e:
        # Bubble up unknown errors (visible in admin and status API)
        job.status = "failed"
        job.error_text = f"{type(e).__name__}: {e}"
        job.save(update_fields=["status", "error_text", "updated_at"])
        raise
