from django.contrib import admin

# Register your models here.

"""
Admin registrations to inspect your data in the Django admin UI.
"""

from django.contrib import admin
from .models import Court, Case, CaseSnapshot, CivilSearchJob

@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    search_fields = ("name", "slug")

@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("court", "gak_number", "gak_year", "procedure", "subject")
    search_fields = ("gak_number", "gak_year", "subject")

@admin.register(CaseSnapshot)
class CaseSnapshotAdmin(admin.ModelAdmin):
    list_display = ("case", "scraped_at", "scraper_version")

@admin.register(CivilSearchJob)
class CivilSearchJobAdmin(admin.ModelAdmin):
    list_display = ("client_name", "court", "gak_number", "gak_year", "status", "created_at")
    list_filter = ("status", "court")
    search_fields = ("client_name", "gak_number")
