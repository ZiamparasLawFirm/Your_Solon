from django.conf import settings
from django.db import models

# Create your models here.

"""
Data model for Civil queries (Αστικά):

- Court: Courts pulled from SOLON 'Κατάστημα'
- Case: Unique by (court, gak_number, gak_year)
- CaseSnapshot: versioned snapshots of scraped data for auditing
- CivilSearchJob: per-user search job tracking + status
"""

from django.db import models
from django.utils import timezone

class Court(models.Model):
    # Display name as shown on SOLON's Κατάστημα dropdown (e.g., 'Πρωτοδικείο Αθηνών')
    name = models.CharField(max_length=255, unique=True)
    # Slug used internally for stable URLs/identifiers; derived from name
    slug = models.SlugField(max_length=255, unique=True)
    # If SOLON exposes a stable code (optional; blank until discovered)
    solon_code = models.CharField(max_length=64, blank=True)
    # Allows soft-disabling a court without deleting it
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name

class Case(models.Model):
    # Uniqueness is (court, ΓΑΚ, Έτος)
    court = models.ForeignKey(Court, on_delete=models.PROTECT, related_name="cases")
    gak_number = models.CharField(max_length=20)
    gak_year = models.PositiveIntegerField()

    # Optional fields scraped from SOLON details
    procedure = models.CharField(max_length=255, blank=True)      # Διαδικασία
    subject = models.CharField(max_length=255, blank=True)        # Αντικείμενο
    pleading_type = models.CharField(max_length=255, blank=True)  # Είδος Δικογράφου
    eak_number = models.CharField(max_length=20, blank=True)
    eak_year = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["court", "gak_number", "gak_year"],
                name="uniq_case_by_court_gak_year",
            )
        ]

    def __str__(self) -> str:
        return f"{self.court} — ΓΑΚ {self.gak_number}/{self.gak_year}"

class CaseSnapshot(models.Model):
    # Versioned payload of scraped fields for auditability & debugging
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="snapshots")
    data_json = models.JSONField()  # Raw dict of the fields as scraped
    scraped_at = models.DateTimeField(default=timezone.now)
    scraper_version = models.CharField(max_length=32, default="v1")
    created_by_username = models.CharField(max_length=150, blank=True)  # who initiated the scrape

class CivilSearchJob(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='civil_jobs', null=True, blank=True)
    """
    Tracks a user's search request and its lifecycle:
    - queued -> running -> done/failed
    Links to the Case and the chosen CaseSnapshot when complete.
    """
    STATUS = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("done", "Done"),
        ("failed", "Failed"),
    ]

    client_name = models.CharField(max_length=255)
    court = models.ForeignKey(Court, on_delete=models.PROTECT)
    gak_number = models.CharField(max_length=20)
    gak_year = models.PositiveIntegerField()

    status = models.CharField(max_length=16, choices=STATUS, default="queued")
    error = models.TextField(blank=True, default="")
    error_text = models.TextField(blank=True)

    case = models.ForeignKey(Case, null=True, blank=True, on_delete=models.SET_NULL)
    snapshot = models.ForeignKey(CaseSnapshot, null=True, blank=True, on_delete=models.SET_NULL)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class UserCase(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_cases')
    case = models.ForeignKey('Case', on_delete=models.CASCADE, related_name='user_cases')
    client_name = models.CharField(max_length=255)
    last_snapshot = models.ForeignKey('CaseSnapshot', null=True, blank=True, on_delete=models.SET_NULL, related_name='user_cases_last')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'case')

    def __str__(self) -> str:
        return f"{self.client_name} — {self.case}"

