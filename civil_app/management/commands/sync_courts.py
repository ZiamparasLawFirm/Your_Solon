from django.core.management.base import BaseCommand
from django.utils.text import slugify
from playwright.sync_api import sync_playwright
from civil_app.models import Court

SOLON_TRACK_URL = "https://extapps.solon.gov.gr/mojwp/faces/TrackLdoPublic"

class Command(BaseCommand):
    help = "Populate/refresh the Court list from SOLON 'Κατάστημα' dropdown."

    def handle(self, *args, **opts):
        names = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(locale="el-GR")
            page.goto(SOLON_TRACK_URL, wait_until="domcontentloaded", timeout=45000)
            sel = page.get_by_label("Κατάστημα", exact=False) or page.locator("select").first
            opts = sel.locator("option")
            for i in range(opts.count()):
                t = opts.nth(i).inner_text().strip()
                if not t or t.lower() in ("--", "επιλέξτε", "επιλογή"):
                    continue
                names.append(t)
            browser.close()

        added = 0
        for n in names:
            Court.objects.update_or_create(
                name=n,
                defaults={"slug": slugify(n, allow_unicode=True), "is_active": True},
            )
            added += 1
        self.stdout.write(self.style.SUCCESS(f"Synced {added} courts."))
