"""
URL routes for civil_app.
"""
from django.urls import path
from .views import CivilSearchView, job_status_api, job_status_page

app_name = "civil_app"

urlpatterns = [
    path("", CivilSearchView.as_view(), name="search"),
    path("jobs/<int:job_id>/", job_status_page, name="job_status_page"),
    path("api/jobs/<int:job_id>/", job_status_api, name="job_status_api"),
]
