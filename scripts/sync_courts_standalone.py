"""
Standalone loader to sync Courts from SOLON without relying on Django's management command registry.
It auto-detects your Django settings package even if the project was named differently.

Usage:
  python scripts/sync_courts_standalone.py
"""

import os
import sys
from pathlib import Path

# --- Ensure project root is on sys.path ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def guess_settings_module() -> str:
    """
    Try to determine the correct DJANGO_SETTINGS_MODULE.
    Priority:
      1) Existing env var (if valid)
      2) Common package names
      3) Any folder in project root that contains a settings.py
    """
    # 1) If already set, trust it
    env = os.environ.get("DJANGO_SETTINGS_MODULE")
    if env:
        return env

    # 2) Common names we used in this thread
    candidates = ["your_solon", "solon_site", "config_site", "mysolonlike"]
    for pkg in candidates:
        if (PROJECT_ROOT / pkg / "settings.py").exists():
            return f"{pkg}.settings"

    # 3) Scan any directory with a settings.py
    for p in PROJECT_ROOT.iterdir():
        if p.is_dir() and (p / "settings.py").exists():
            return f"{p.name}.settings"

    raise RuntimeError("Could not locate Django settings module. Make sure your project package exists next to manage.py and contains settings.py")

# Resolve and set DJANGO_SETTINGS_MODULE
settings_module = guess_settings_module()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

# --- Now initialize Django ---
import django  # noqa: E402
django.setup()

# After setup, we can import ORM models
from django.utils.text import slugify  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from civil_app.models import Court  # noqa: E402

SOLON_TRACK_URL = "https://extapps.solon.gov.gr/mojwp/faces/TrackLdoPublic"

def main() -> None:
    added = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(locale="el-GR")
        page.goto(SOLON_TRACK_URL, wait_until="domcontentloaded", timeout=45000)

        # Find Κατάστημα <select>
        select = page.get_by_label("Κατάστημα", exact=False)
        if not select.count():
            select = page.locator("select").first

        options = select.locator("option")
        for i in range(options.count()):
            text = options.nth(i).inner_text().strip()
            if not text or text.lower() in ("--", "επιλέξτε", "επιλογή"):
                continue
            Court.objects.update_or_create(
                name=text,
                defaults={"slug": slugify(text, allow_unicode=True), "is_active": True},
            )
            added += 1

        browser.close()

    print(f"[OK] DJANGO_SETTINGS_MODULE={settings_module}")
    print(f"Synced {added} courts.")

if __name__ == "__main__":
    main()
