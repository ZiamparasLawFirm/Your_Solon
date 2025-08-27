"""
Management command to fetch the 'Κατάστημα' (Court) options from SOLON's Track page
and upsert them into the Court model.

Run:  python manage.py sync_courts
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from playwright.sync_api import sync_playwright
from civil_app.models import Court

SOLON_TRACK_URL = "https://extapps.solon.gov.gr/mojwp/faces/TrackLdoPublic"

class Command(BaseCommand):
    help = "Populate/refresh the Court list from SOLON 'Κατάστημα' dropdown."

    def handle(self, *args, **opts):
        # Launch a headless Chromium via Playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(locale="el-GR")

            # Load the SOLON Track page
            page.goto(SOLON_TRACK_URL, wait_until="domcontentloaded", timeout=45000)

            # Try to locate the courts <select> by label; fallback to first <select>
            select = page.get_by_label("Κατάστημα", exact=False)
            if not select.count():
                select = page.locator("select").first

            # Iterate over option elements and persist each valid court
            options = select.locator("option")
            count = options.count()
            added = 0
            for i in range(count):
                text = options.nth(i).inner_text().strip()
                # Skip placeholder options like 'Επιλέξτε'
                if not text or text.lower() in ("--", "επιλέξτε", "επιλογή"):
                    continue

                Court.objects.update_or_create(
                    name=text,
                    defaults={"slug": slugify(text, allow_unicode=True), "is_active": True},
                )
                added += 1

            browser.close()

        self.stdout.write(self.style.SUCCESS(f"Synced {added} courts."))
